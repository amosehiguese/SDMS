from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum, Q, Avg, F
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import csv
from emails.tasks import send_order_status_update_task
from orders.models import Order, OrderStatusLog
from store.models import Product, Category
from django.contrib.auth.models import User

import logging

logger = logging.getLogger(__name__)


@staff_member_required
def analytics_dashboard(request):
    """Main analytics dashboard"""
    # Get date filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status_filter = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    
    # Set default date range (last 30 days)
    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).date()
    else:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    
    if not date_to:
        date_to = timezone.now().date()
    else:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Base queryset
    orders = Order.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).select_related('user').prefetch_related('items__product')
    
    # Apply filters
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    if category_filter:
        orders = orders.filter(items__product__category__slug=category_filter)
    
    # Calculate stats
    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
    average_order_value = total_revenue / total_orders if total_orders > 0 else Decimal('0')
    
    # Status breakdown
    status_breakdown = Order.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).values('status').annotate(count=Count('id')).order_by('status')
    
    # Flash sale performance - Use Python aggregation instead of database
    flash_sale_products_data = []
    flash_sale_products = Product.objects.filter(
        flash_sale_enabled=True,
        orderitem__order__created_at__date__gte=date_from,
        orderitem__order__created_at__date__lte=date_to
    ).distinct().prefetch_related('orderitem_set__order')
    
    for product in flash_sale_products:
        # Calculate totals in Python
        order_items = product.orderitem_set.filter(
            order__created_at__date__gte=date_from,
            order__created_at__date__lte=date_to
        )
        total_sold = sum(item.quantity for item in order_items)
        revenue = sum(item.price * item.quantity for item in order_items)
        
        if total_sold > 0:  # Only include products that have sales
            flash_sale_products_data.append({
                'product': product,
                'total_sold': total_sold,
                'revenue': revenue
            })
    
    # Sort by total sold
    flash_sale_products_data.sort(key=lambda x: x['total_sold'], reverse=True)
    flash_sale_products_data = flash_sale_products_data[:10]
    
    # Top selling products - Use Python aggregation
    top_products_data = []
    products_with_sales = Product.objects.filter(
        orderitem__order__created_at__date__gte=date_from,
        orderitem__order__created_at__date__lte=date_to
    ).distinct().select_related('category').prefetch_related('orderitem_set__order')
    
    for product in products_with_sales:
        # Calculate totals in Python
        order_items = product.orderitem_set.filter(
            order__created_at__date__gte=date_from,
            order__created_at__date__lte=date_to
        )
        total_sold = sum(item.quantity for item in order_items)
        revenue = sum(item.price * item.quantity for item in order_items)
        
        if total_sold > 0:  # Only include products that have sales
            top_products_data.append({
                'product': product,
                'total_sold': total_sold,
                'revenue': revenue
            })
    
    # Sort by total sold
    top_products_data.sort(key=lambda x: x['total_sold'], reverse=True)
    top_products_data = top_products_data[:10]
    
    # Get categories and order statuses for filters
    categories = Category.objects.filter(is_active=True, parent=None)
    order_statuses = Order.STATUS_CHOICES
    
    # Get orders that need admin action (paid but not shipped/delivered)
    pending_orders = Order.objects.filter(
        status__in=['paid', 'shipped'],
        fulfillment_type='deliver'
    ).select_related('user').order_by('status', 'created_at')
    
    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'average_order_value': average_order_value,
        'status_breakdown': status_breakdown,
        'flash_sale_products': flash_sale_products_data,
        'top_products': top_products_data,
        'categories': categories,
        'order_statuses': order_statuses,
        'pending_orders': pending_orders,
        'date_from': date_from,
        'date_to': date_to,
        'status_filter': status_filter,
        'category_filter': category_filter,
    }
    
    return render(request, 'core/analytics_dashboard.html', context)


@staff_member_required
def analytics_data(request):
    """AJAX endpoint for chart data"""
    period = request.GET.get('period', 'daily')  # daily, weekly, monthly
    days = int(request.GET.get('days', 30))
    
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Generate date range
    dates = []
    labels = []
    current_date = start_date
    
    if period == 'daily':
        while current_date <= end_date:
            dates.append(current_date)
            labels.append(current_date.strftime('%m/%d'))
            current_date += timedelta(days=1)
    elif period == 'weekly':
        while current_date <= end_date:
            dates.append(current_date)
            labels.append(f"Week {current_date.strftime('%U')}")
            current_date += timedelta(weeks=1)
    elif period == 'monthly':
        while current_date <= end_date:
            dates.append(current_date)
            labels.append(current_date.strftime('%b %Y'))
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
    # Get sales data
    sales_data = []
    revenue_data = []
    
    for date in dates:
        if period == 'daily':
            orders = Order.objects.filter(created_at__date=date)
        elif period == 'weekly':
            week_start = date
            week_end = date + timedelta(days=6)
            orders = Order.objects.filter(created_at__date__gte=week_start, created_at__date__lte=week_end)
        elif period == 'monthly':
            if date.month == 12:
                next_month = date.replace(year=date.year + 1, month=1)
            else:
                next_month = date.replace(month=date.month + 1)
            orders = Order.objects.filter(created_at__date__gte=date, created_at__date__lt=next_month)
        
        count = orders.count()
        revenue = orders.aggregate(total=Sum('total'))['total'] or 0
        
        sales_data.append(count)
        revenue_data.append(float(revenue))
    
    return JsonResponse({
        'labels': labels,
        'sales_data': sales_data,
        'revenue_data': revenue_data
    })


@staff_member_required
def update_order_status(request):
    """Update order status via AJAX"""
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        try:
            order = get_object_or_404(Order, id=order_id)
            old_status = order.status
            
            # Validate status transition
            if new_status == 'delivered' and old_status != 'shipped':
                return JsonResponse({
                    'success': False,
                    'message': 'Order must be shipped before it can be delivered'
                })
            
            # Update order status
            order.status = new_status
            
            # Update timestamps
            if new_status == 'shipped':
                order.shipped_at = timezone.now()
            elif new_status == 'delivered':
                order.delivered_at = timezone.now()
            
            order.save()

            try:
                send_order_status_update_task.delay(str(order.id), old_status, new_status)
                logger.info(f"Order status update email queued for order {order.id}: {old_status} -> {new_status}")
            except Exception as e:
                logger.error(f"Failed to queue status update email for order {order.id}: {str(e)}")
                        
            # Log status change
            OrderStatusLog.objects.create(
                order=order,
                previous_status=old_status,
                new_status=new_status,
                changed_by=request.user,
                notes=notes
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Order {order.order_number} status updated to {new_status}'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error updating order: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


@staff_member_required
def export_analytics(request):
    """Export analytics data as CSV"""
    export_type = request.GET.get('type', 'orders')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Set default date range
    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).date()
    else:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    
    if not date_to:
        date_to = timezone.now().date()
    else:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    response = HttpResponse(content_type='text/csv')
    
    if export_type == 'orders':
        response['Content-Disposition'] = f'attachment; filename="orders_{date_from}_{date_to}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Order Number', 'Customer Email', 'Status', 'Fulfillment Type',
            'Total Amount', 'Created Date', 'Shipped Date', 'Delivered Date'
        ])
        
        orders = Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to
        ).select_related('user').order_by('-created_at')
        
        for order in orders:
            writer.writerow([
                order.order_number,
                order.user.email,
                order.get_status_display(),
                order.get_fulfillment_type_display(),
                str(order.total),
                order.created_at.strftime('%Y-%m-%d %H:%M'),
                order.shipped_at.strftime('%Y-%m-%d %H:%M') if order.shipped_at else '',
                order.delivered_at.strftime('%Y-%m-%d %H:%M') if order.delivered_at else ''
            ])
    
    elif export_type == 'products':
        response['Content-Disposition'] = f'attachment; filename="products_performance_{date_from}_{date_to}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Product Title', 'Category', 'Units Sold', 'Revenue',
            'Is Flash Sale', 'Stock Quantity'
        ])
        
        # Use the same Python aggregation approach as in analytics_dashboard
        products_with_sales = Product.objects.filter(
            orderitem__order__created_at__date__gte=date_from,
            orderitem__order__created_at__date__lte=date_to
        ).distinct().select_related('category').prefetch_related('orderitem_set__order')
        
        # Build product data list
        product_data = []
        for product in products_with_sales:
            # Calculate totals in Python
            order_items = product.orderitem_set.filter(
                order__created_at__date__gte=date_from,
                order__created_at__date__lte=date_to
            )
            total_sold = sum(item.quantity for item in order_items)
            revenue = sum(item.price * item.quantity for item in order_items)
            
            if total_sold > 0:  # Only include products that have sales
                product_data.append({
                    'product': product,
                    'total_sold': total_sold,
                    'revenue': revenue
                })
        
        # Sort by total sold
        product_data.sort(key=lambda x: x['total_sold'], reverse=True)
        
        # Write to CSV
        for item in product_data:
            product = item['product']
            writer.writerow([
                product.title,
                product.category.name if product.category else 'No Category',
                item['total_sold'],
                str(item['revenue']),
                'Yes' if hasattr(product, 'has_active_flash_sale') and product.has_active_flash_sale() else 'No',
                product.stock_quantity
            ])
    
    elif export_type == 'sales_summary':
        response['Content-Disposition'] = f'attachment; filename="sales_summary_{date_from}_{date_to}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Orders Count', 'Revenue', 'Average Order Value'])
        
        current_date = date_from
        while current_date <= date_to:
            orders = Order.objects.filter(created_at__date=current_date)
            count = orders.count()
            revenue = orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
            avg_order = revenue / count if count > 0 else Decimal('0')
            
            writer.writerow([
                current_date.strftime('%Y-%m-%d'),
                count,
                str(revenue),
                str(avg_order)
            ])
            current_date += timedelta(days=1)
    
    elif export_type == 'emails':
        response['Content-Disposition'] = f'attachment; filename="customer_emails_{date_from}_{date_to}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Email', 'First Name', 'Last Name', 'Total Orders', 'Total Spent', 'Last Order Date'])
        
        # Get unique customers with orders in the date range
        customers = User.objects.filter(
            orders__created_at__date__gte=date_from,
            orders__created_at__date__lte=date_to
        ).distinct().select_related().prefetch_related('orders')
        
        for customer in customers:
            customer_orders = customer.orders.filter(
                created_at__date__gte=date_from,
                created_at__date__lte=date_to
            )
            total_orders = customer_orders.count()
            total_spent = customer_orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
            last_order = customer_orders.order_by('-created_at').first()
            
            writer.writerow([
                customer.email,
                customer.first_name or '',
                customer.last_name or '',
                total_orders,
                str(total_spent),
                last_order.created_at.strftime('%Y-%m-%d') if last_order else ''
            ])
    
    return response