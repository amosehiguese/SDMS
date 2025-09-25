from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Count
import json

from emails.tasks import send_sell_item_notification_task, send_user_email_task

from .models import SellItemSubmission, SellItemImage
from orders.models import Order
from store.models import Product, ProductImage, Category

import logging

logger = logging.getLogger(__name__)

@login_required
def sell_item_list(request):
    """List user's sell submissions"""
    submissions = SellItemSubmission.objects.filter(user=request.user).prefetch_related('images')
    return render(request, 'sell_items/sell_item_list.html', {'submissions': submissions})

@login_required
def submit_sell_item(request):
    """Submit an item to sell (own item)"""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Handle category creation/selection
                category = None
                category_input = request.POST.get('category_name', '').strip()
                if category_input:
                    # Create or get category
                    category, created = Category.objects.get_or_create(
                        name__iexact=category_input,  # Case insensitive lookup
                        defaults={
                            'name': category_input,
                            'is_active': True
                        }
                    )
                
                # Create submission
                submission = SellItemSubmission.objects.create(
                    user=request.user,
                    title=request.POST.get('title'),
                    description=request.POST.get('description'),
                    category=category,
                    price=request.POST.get('price'),
                    stock_quantity=request.POST.get('stock_quantity', 1),
                    weight=request.POST.get('weight') if request.POST.get('weight') else None,
                    dimensions=request.POST.get('dimensions'),
                    bank_name=request.POST.get('bank_name'),
                    account_number=request.POST.get('account_number'),
                    account_holder_name=request.POST.get('account_holder_name'),
                    source='own_item'
                )
                
                # Handle image uploads
                images = request.FILES.getlist('images')
                for i, image in enumerate(images):
                    SellItemImage.objects.create(
                        submission=submission,
                        image=image,
                        is_primary=(i == 0),
                        sort_order=i
                    )

                try:
                    send_sell_item_notification_task.delay(str(submission.id))
                    logger.info(f"Sell item notification emails queued for submission {submission.id}")
                except Exception as e:
                    logger.error(f"Failed to queue sell item emails for submission {submission.id}: {str(e)}")
                
                messages.success(request, 'Your item has been submitted for review!')
                return redirect('sell_items:sell_item_list')
                
        except Exception as e:
            messages.error(request, 'Error submitting item. Please try again.')
    
    return render(request, 'sell_items/submit_sell_item.html', {
        'categories': Category.objects.filter(is_active=True),
    })

@login_required
def submit_held_asset_sell(request, order_id):
    """Submit a held asset for selling back"""
    order = get_object_or_404(Order, id=order_id, user=request.user, fulfillment_type='hold_asset', status='paid')
    
    if request.method == 'POST':
        try:
            # Check if already submitted
            if SellItemSubmission.objects.filter(
                held_asset_order=order, 
                status__in=['pending', 'accepted']
            ).exists():
                messages.warning(request, 'This asset already has a pending or accepted submission.')
                return redirect('sell_items:sell_item_list')
            
            with transaction.atomic():
                # Get the first order item for display
                order_item = order.items.first()
                if not order_item:
                    messages.error(request, 'Invalid order.')
                    return redirect('orders:held_assets')
                
                # Validate stock quantity
                stock_quantity = int(request.POST.get('stock_quantity', 1))
                available_qty = order_item.get_available_quantity()
                if stock_quantity > available_qty:
                    messages.error(request, f'Stock quantity cannot exceed {available_qty} (available quantity after considering pending submissions).')
                    return render(request, 'sell_items/submit_held_asset_sell.html', {
                        'order': order,
                        'order_item': order_item,
                        'available_quantity': available_qty
                    })

                title = request.POST.get('title')
                if title is None or  title == "":
                    messages.error(request, 'Please set product title')
                    return render(request, 'sell_items/submit_held_asset_sell.html', {
                        'order': order,
                        'order_item': order_item,
                        'available_quantity': available_qty
                    })
                elif title == order_item.product.title:
                    messages.error(request, 'Product title same with original. Change it')
                    return render(request, 'sell_items/submit_held_asset_sell.html', {
                        'order': order,
                        'order_item': order_item,
                        'available_quantity': available_qty
                    })

                
                
                submission = SellItemSubmission.objects.create(
                    user=request.user,
                    title=title,
                    description=request.POST.get('description', order_item.product.description),
                    category=order_item.product.category,
                    price=request.POST.get('price'),
                    stock_quantity=stock_quantity,
                    weight=order_item.product.weight,
                    dimensions=order_item.product.dimensions,
                    bank_name=request.POST.get('bank_name'),
                    account_number=request.POST.get('account_number'),
                    account_holder_name=request.POST.get('account_holder_name'),
                    source='held_asset',
                    held_asset_order=order
                )
                
                # Copy images from original product
                for i, product_image in enumerate(order_item.product.images.all()):
                    # Copy the image file
                    image_content = product_image.image.read()
                    new_image_name = f"sell_items/{submission.id}_{i}_{product_image.image.name.split('/')[-1]}"
                    new_image_file = ContentFile(image_content)
                    saved_path = default_storage.save(new_image_name, new_image_file)
                    
                    SellItemImage.objects.create(
                        submission=submission,
                        image=saved_path,
                        alt_text=product_image.alt_text,
                        is_primary=product_image.is_primary,
                        sort_order=product_image.sort_order
                    )
                
                try:
                    send_sell_item_notification_task.delay(str(submission.id))
                    logger.info(f"Sell item notification emails queued for submission {submission.id}")
                except Exception as e:
                    logger.error(f"Failed to queue sell item emails for submission {submission.id}: {str(e)}")

                messages.success(request, 'Your held asset has been submitted for selling!')
                return redirect('sell_items:sell_item_list')
                
        except Exception as e:
            messages.error(request, 'Error submitting asset for selling.')
    
    # Get the first order item for display
    order_item = order.items.first()
    return render(request, 'sell_items/submit_held_asset_sell.html', {
        'order': order,
        'order_item': order_item
    })

@login_required
def sell_submission_detail(request, submission_id):
    """View sell submission details"""
    submission = get_object_or_404(SellItemSubmission, id=submission_id, user=request.user)
    return render(request, 'sell_items/sell_submission_detail.html', {'submission': submission})

@staff_member_required
def admin_submissions(request):
    """Admin page to view all sell submissions"""
    status_filter = request.GET.get('status', 'pending')
    submissions = SellItemSubmission.objects.filter(status=status_filter).prefetch_related('images', 'user')

    counts = SellItemSubmission.objects.values('status').annotate(count=Count('id'))
    
    status_counts = {item['status']: item['count'] for item in counts}

    return render(request, 'sell_items/admin_submissions.html', {
        'submissions': submissions,
        'current_status': status_filter,
        'status_counts': status_counts, 
    })

@staff_member_required
def admin_review_submission(request, submission_id):
    """Admin review submission detail"""
    submission = get_object_or_404(SellItemSubmission, id=submission_id)
    return render(request, 'sell_items/admin_review_submission.html', {'submission': submission})

@login_required
def update_bank_details(request, submission_id):
    """Update bank account details for a submission"""
    submission = get_object_or_404(SellItemSubmission, id=submission_id, user=request.user)
    
    if request.method == 'POST':
        try:
            submission.bank_name = request.POST.get('bank_name')
            submission.account_number = request.POST.get('account_number')
            submission.account_holder_name = request.POST.get('account_holder_name')
            submission.save()
            
            messages.success(request, 'Bank account details updated successfully!')
            return redirect('sell_items:sell_submission_detail', submission_id=submission_id)
            
        except Exception as e:
            messages.error(request, 'Error updating bank details. Please try again.')
    
    return render(request, 'sell_items/update_bank_details.html', {'submission': submission})

@login_required
def edit_sell_submission(request, submission_id):
    """Edit and resubmit a sell item submission"""
    submission = get_object_or_404(SellItemSubmission, id=submission_id, user=request.user)
    
    # Only allow editing of rejected or pending submissions
    if submission.status not in ['pending', 'rejected']:
        messages.error(request, 'This submission cannot be edited.')
        return redirect('sell_items:sell_submission_detail', submission_id=submission_id)
    
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            if title is None or title == '':
                messages.error(request, 'Please set product title')
                return render(request, 'sell_items/edit_sell_submission.html', {
                    'submission': submission,
                    'categories': Category.objects.filter(is_active=True)
                })                

            with transaction.atomic():
                # Update submission fields
                submission.title = request.POST.get('title')
                submission.description = request.POST.get('description')
                submission.price = request.POST.get('price')
                submission.stock_quantity = request.POST.get('stock_quantity', 1)
                submission.weight = request.POST.get('weight') if request.POST.get('weight') else None
                submission.dimensions = request.POST.get('dimensions')
                submission.bank_name = request.POST.get('bank_name')
                submission.account_number = request.POST.get('account_number')
                submission.account_holder_name = request.POST.get('account_holder_name')
                
                # For held assets, validate stock quantity
                if submission.source == 'held_asset':
                    stock_quantity = int(submission.stock_quantity)
                    available_qty = submission.max_allowed_quantity
                    if stock_quantity > available_qty:
                        messages.error(request, f'Stock quantity cannot exceed {available_qty}.')
                        return render(request, 'sell_items/edit_sell_submission.html', {
                            'submission': submission,
                            'categories': Category.objects.filter(is_active=True)
                        })
                
                # Handle category for own items
                if submission.source == 'own_item':
                    category_input = request.POST.get('category_name', '').strip()
                    if category_input:
                        category, created = Category.objects.get_or_create(
                            name__iexact=category_input,
                            defaults={'name': category_input, 'is_active': True}
                        )
                        submission.category = category
                
                # Handle new image uploads if provided
                images = request.FILES.getlist('images')
                if images:
                    # Remove existing images if new ones are uploaded
                    submission.images.all().delete()
                    for i, image in enumerate(images):
                        SellItemImage.objects.create(
                            submission=submission,
                            image=image,
                            is_primary=(i == 0),
                            sort_order=i
                        )
                
                # Reset status to pending and clear admin notes
                submission.status = 'pending'
                submission.admin_notes = ''
                submission.reviewed_by = None
                submission.reviewed_at = None
                submission.save()

                try:
                    send_sell_item_notification_task.delay(str(submission.id))
                    logger.info(f"Sell item resubmission notification emails queued for submission {submission.id}")
                except Exception as e:
                    logger.error(f"Failed to queue resubmission emails for submission {submission.id}: {str(e)}")
                
                messages.success(request, 'Your submission has been updated and resubmitted for review!')
                return redirect('sell_items:sell_submission_detail', submission_id=submission_id)
                
        except Exception as e:
            messages.error(request, 'Error updating submission. Please try again.')
    
    context = {
        'submission': submission,
        'categories': Category.objects.filter(is_active=True) if submission.source == 'own_item' else None
    }
    return render(request, 'sell_items/edit_sell_submission.html', context)

@require_http_methods(["POST"])
@staff_member_required
def update_submission_status(request):
    """AJAX endpoint to update submission status"""
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')
        status = data.get('status')
        admin_notes = data.get('admin_notes', '')
        
        submission = get_object_or_404(SellItemSubmission, id=submission_id)
        
        submission.status = status
        submission.admin_notes = admin_notes
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.save()

        try:
            context = {
                'submission_id': str(submission.id),
                'title': submission.title,
                'item_name': getattr(submission, 'item_name', ''),
                'status': submission.status,
                'admin_notes': admin_notes,
                'reviewed_at': submission.reviewed_at,
                'user_email': submission.user.email,
                'user_first_name': submission.user.first_name or '',
                'user_last_name': submission.user.last_name or '',
            }
            
            if status == 'accepted':
                send_user_email_task.delay('sell_item_approved', submission.user.id, context)
                logger.info(f"Sell item approval email queued for submission {submission.id}")
            elif status == 'rejected':
                context.update({
                    'rejection_reason': admin_notes,
                    'rejected_at': submission.reviewed_at,
                })
                send_user_email_task.delay('sell_item_rejected', submission.user.id, context)
                logger.info(f"Sell item rejection email queued for submission {submission.id}")

        except Exception as e:
            logger.error(f"Failed to queue status update email for submission {submission.id}: {str(e)}")
        

        return JsonResponse({'success': True, 'message': 'Status updated successfully'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to update status'})

@require_http_methods(["POST"])
@staff_member_required
def create_product_from_submission(request):
    """AJAX endpoint to create product from accepted submission"""
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')
        admin_price = data.get('admin_price')
        
        submission = get_object_or_404(SellItemSubmission, id=submission_id, status='accepted')
        
        with transaction.atomic():
            # Create product
            product = Product.objects.create(
                title=submission.title,
                description=submission.description,
                category=submission.category,
                price=admin_price or submission.price,
                stock_quantity=submission.stock_quantity,
                weight=submission.weight,
                dimensions=submission.dimensions,
                is_active=True
            )

            if submission.source == 'held_asset' and submission.held_asset_order:
                order_item = submission.held_asset_order.items.first()
                if order_item and order_item.quantity >= submission.stock_quantity:
                    order_item.quantity -= submission.stock_quantity
                    order_item.save()
                    
                    # If quantity becomes 0, we might want to mark something
                    if order_item.quantity == 0:
                        # Optional: Add a flag or status to indicate fully sold
                        pass
            
            # Copy images
            for sell_image in submission.images.all():
                ProductImage.objects.create(
                    product=product,
                    image=sell_image.image,
                    alt_text=sell_image.alt_text,
                    is_primary=sell_image.is_primary,
                    sort_order=sell_image.sort_order
                )
            
            return JsonResponse({
                'success': True, 
                'message': 'Product created successfully',
                'product_id': str(product.id)
            })
            
    except Exception as e:
        print(e)
        return JsonResponse({'success': False, 'error': 'Failed to create product'})