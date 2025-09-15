from datetime import timezone, timedelta
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.sessions.models import Session
from django.contrib import messages
from django.urls import reverse

from core.models import SiteConfiguration
from .models import Order, OrderItem, Cart, CartItem, ShippingAddress
from store.models import Product
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

def get_or_create_cart(request):
    """Get or create cart for user (authenticated or anonymous)"""
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
    else:
        # For anonymous users, use session key
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        cart, created = Cart.objects.get_or_create(session_key=session_key)
    return cart

def cart_view(request):
    """Display shopping cart"""
    cart = get_or_create_cart(request)
    return render(request, 'orders/cart.html', {'cart': cart})

def cart_sidebar(request):
    """AJAX endpoint to get cart sidebar content"""
    cart = get_or_create_cart(request)
    return render(request, 'orders/cart_sidebar.html', {'cart': cart})

@require_http_methods(["POST"])
def add_to_cart(request):
    """AJAX endpoint to add product to cart"""
    try:
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        buy_now = request.POST.get('buy_now', 'false').lower() == 'true'
        
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        if not product.can_purchase(quantity):
            return JsonResponse({
                'success': False, 
                'error': 'Product is out of stock or insufficient quantity available'
            })
        
        cart = get_or_create_cart(request)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, 
            product=product,
            defaults={'quantity': quantity}
        )
        
        if not created:
            new_quantity = cart_item.quantity + quantity
            if not product.can_purchase(new_quantity):
                return JsonResponse({
                    'success': False, 
                    'error': 'Cannot add more items. Insufficient stock.'
                })
            cart_item.quantity = new_quantity
            cart_item.save()
        
        response_data = {
            'success': True,
            'cart_total_items': cart.get_total_items(),
            'cart_subtotal': str(cart.get_subtotal()),
            'message': f'{product.title} added to cart'
        }
        
        # If buy_now is True, redirect to checkout
        if buy_now:
            response_data['redirect_url'] = reverse('orders:checkout')
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

def get_cart_count(request):
    """Get cart count for both authenticated and anonymous users"""
    try:
        cart = get_or_create_cart(request)
        return JsonResponse({
            'success': True,
            'cart_count': cart.get_total_items()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

@require_http_methods(["POST"])
def update_cart_item(request):
    """AJAX endpoint to update cart item quantity"""
    try:
        item_id = request.POST.get('item_id')
        quantity = int(request.POST.get('quantity', 1))
        
        if request.user.is_authenticated:
            cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        else:
            if not request.session.session_key:
                return JsonResponse({'success': False, 'error': 'Session not found'})
            cart_item = get_object_or_404(CartItem, id=item_id, cart__session_key=request.session.session_key)
        
        if quantity <= 0:
            cart_item.delete()
            return JsonResponse({
                'success': True,
                'action': 'removed',
                'cart_total_items': cart_item.cart.get_total_items(),
                'cart_subtotal': str(cart_item.cart.get_subtotal())
            })
        
        if not cart_item.product.can_purchase(quantity):
            return JsonResponse({
                'success': False, 
                'error': 'Insufficient stock for requested quantity'
            })
        
        cart_item.quantity = quantity
        cart_item.save()
        
        return JsonResponse({
            'success': True,
            'action': 'updated',
            'item_total': str(cart_item.get_total_price()),
            'cart_total_items': cart_item.cart.get_total_items(),
            'cart_subtotal': str(cart_item.cart.get_subtotal())
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})


@require_http_methods(["POST"])
def remove_from_cart(request):
    """AJAX endpoint to remove item from cart"""
    try:
        item_id = request.POST.get('item_id')
        
        if request.user.is_authenticated:
            cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        else:
            if not request.session.session_key:
                return JsonResponse({'success': False, 'error': 'Session not found'})
            cart_item = get_object_or_404(CartItem, id=item_id, cart__session_key=request.session.session_key)
        
        cart = cart_item.cart
        cart_item.delete()
        
        return JsonResponse({
            'success': True,
            'cart_total_items': cart.get_total_items(),
            'cart_subtotal': str(cart.get_subtotal())
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

def checkout(request):
    """Checkout page"""
    if not request.user.is_authenticated:
        messages.info(request, 'Please log in to proceed to checkout.')
        return redirect('account_login')
    
    cart = get_or_create_cart(request)
    
    if not cart.items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('orders:cart')
    
    # Check stock availability for all items
    for item in cart.items.all():
        if not item.product.can_purchase(item.quantity):
            messages.error(request, f'{item.product.title} is out of stock or has insufficient quantity.')
            return redirect('orders:cart')
    
    shipping_addresses = request.user.shipping_addresses.all()
    
    from core.models import SiteConfiguration
    site_config = SiteConfiguration.get_config()
    
    return render(request, 'orders/checkout.html', {
        'cart': cart,
        'shipping_addresses': shipping_addresses,
        'site_config': site_config,
    })

@require_http_methods(["POST"])
@login_required
def create_order(request):
    """AJAX endpoint to create order"""
    try:
        print(f"POST data: {request.POST}")  # Debug logging
        
        cart = get_or_create_cart(request)
        
        if not cart.items.exists():
            return JsonResponse({'success': False, 'error': 'Cart is empty'})
        
        fulfillment_type = request.POST.get('fulfillment_type')
        print(f"Fulfillment type: {fulfillment_type}")  # Debug logging
        
        if fulfillment_type not in ['hold_asset', 'deliver']:
            return JsonResponse({'success': False, 'error': f'Invalid fulfillment type: {fulfillment_type}'})
        
        # For delivery orders, validate shipping address
        shipping_address = None
        if fulfillment_type == 'deliver':
            address_id = request.POST.get('shipping_address_id')
            print(f"Address ID: {address_id}")  # Debug logging
            
            if address_id:
                # Using existing address
                try:
                    shipping_address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
                    print(f"Using existing address: {shipping_address}")  # Debug logging
                except:
                    return JsonResponse({'success': False, 'error': 'Invalid shipping address selected'})
            else:
                # Creating new address
                print("Creating new address...")  # Debug logging
                required_fields = ['first_name', 'last_name', 'address_line_1', 'city', 'state', 'country', 'phone', 'email']
                
                # Validate required fields
                missing_fields = []
                for field in required_fields:
                    if not request.POST.get(field):
                        missing_fields.append(field)
                
                if missing_fields:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Missing required fields: {", ".join(missing_fields)}'
                    })
                
                try:
                    shipping_address = ShippingAddress.objects.create(
                        user=request.user,
                        first_name=request.POST.get('first_name'),
                        last_name=request.POST.get('last_name'),
                        email=request.POST.get('email'),
                        phone=request.POST.get('phone'),
                        address_line_1=request.POST.get('address_line_1'),
                        address_line_2=request.POST.get('address_line_2', ''),
                        city=request.POST.get('city'),
                        state=request.POST.get('state'),
                        postal_code=request.POST.get('postal_code', ''),
                        country=request.POST.get('country'),
                        is_default=request.POST.get('is_default') == 'on'
                    )
                    print(f"Created new address: {shipping_address}")  # Debug logging
                except Exception as e:
                    print(f"Error creating address: {str(e)}")  # Debug logging
                    return JsonResponse({'success': False, 'error': f'Error creating shipping address: {str(e)}'})
        
        # Create order
        print("Creating order...")  # Debug logging
        try:
            order = Order.objects.create(
                user=request.user,
                fulfillment_type=fulfillment_type,
                shipping_address=shipping_address,
                customer_notes=request.POST.get('notes', '')
            )
            print(f"Created order: {order.id}")  # Debug logging
        except Exception as e:
            print(f"Error creating order: {str(e)}")  # Debug logging
            return JsonResponse({'success': False, 'error': f'Error creating order: {str(e)}'})
        
        # Create order items
        print("Creating order items...")  # Debug logging
        try:
            for cart_item in cart.items.all():
                if not cart_item.product.can_purchase(cart_item.quantity):
                    order.delete()
                    return JsonResponse({
                        'success': False, 
                        'error': f'{cart_item.product.title} is out of stock'
                    })
                
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.product.get_display_price()
                )
            print("Created order items successfully")  # Debug logging
        except Exception as e:
            print(f"Error creating order items: {str(e)}")  # Debug logging
            order.delete()
            return JsonResponse({'success': False, 'error': f'Error creating order items: {str(e)}'})
        
        # Calculate totals
        print("Calculating totals...")  # Debug logging
        try:
            order.calculate_totals()
            print(f"Order total: {order.total}")  # Debug logging
        except Exception as e:
            print(f"Error calculating totals: {str(e)}")  # Debug logging
            order.delete()
            return JsonResponse({'success': False, 'error': f'Error calculating order totals: {str(e)}'})
        
        # Clear cart
        print("Clearing cart...")  # Debug logging
        try:
            cart.clear()
            print("Cart cleared successfully")  # Debug logging
        except Exception as e:
            print(f"Error clearing cart: {str(e)}")  # Debug logging
            # Don't fail the order creation if cart clearing fails
        
        print("Order creation successful, preparing response...")  # Debug logging
        
        return JsonResponse({
            'success': True,
            'order_id': str(order.id),
            'redirect_url': reverse('payments:paystack_pay', args=[order.id])
        })
        
    except Exception as e:
        print(f"Unexpected error in create_order: {str(e)}")  # Debug logging
        import traceback
        print(traceback.format_exc())  # Full stack trace
        return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'})

@login_required
def order_detail(request, order_id):
    """Order detail page"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/order_detail.html', {'order': order})

@login_required
def order_receipt(request, order_id):
    """
    Displays a printable receipt for a specific order.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)
    site_config = SiteConfiguration.get_config()
    context = {
        'order': order,
        'site_config': site_config,
        'layout': 'component' 
    }
    return render(request, 'orders/order_receipt.html', context)

@login_required
def order_history(request):
    """User's order history with improved, dynamic filtering."""
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product')
    
    # Get filter parameters from the request
    status_filter = request.GET.get('status', '')
    period_filter = request.GET.get('period', '')

    # Apply status filter
    if status_filter and status_filter != 'all':
        orders = orders.filter(status=status_filter)

    # Apply dynamic time period filter
    if period_filter:
        today = timezone.now().date()
        if period_filter == 'last_week':
            # Orders from the last 7 days
            start_date = today - timedelta(days=7)
            orders = orders.filter(created_at__date__gte=start_date)
        elif period_filter == 'last_month':
            # Orders from the last 30 days
            start_date = today - timedelta(days=30)
            orders = orders.filter(created_at__date__gte=start_date)
        elif period_filter == 'last_3_months':
            # Orders from the last 90 days
            start_date = today - timedelta(days=90)
            orders = orders.filter(created_at__date__gte=start_date)
        elif period_filter == 'last_year':
            # Orders from the last 365 days
            start_date = today - timedelta(days=365)
            orders = orders.filter(created_at__date__gte=start_date)

    paginator = Paginator(orders, 5)
    page = request.GET.get('page')
    try:
        orders = paginator.page(page)
    except PageNotAnInteger:
        orders = paginator.page(1)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)

    context = {
        'orders': orders,
        'status_choices': Order.STATUS_CHOICES,
        'current_status': status_filter,
        'current_period': period_filter
    }
    return render(request, 'orders/order_history.html', context)

@login_required
def held_assets(request):
    """User's held assets"""
    held_orders = Order.objects.filter(
        user=request.user,
        fulfillment_type='hold_asset',
        status='paid'
    ).prefetch_related('items__product__images')
    
    # Create a list of assets with proper order association
    held_assets = []
    for order in held_orders:
        for item in order.items.all():
            held_assets.append({
                'order': order,
                'product': item.product,
                'quantity': item.quantity,
                'price': item.price
            })
    
    return render(request, 'orders/held_assets.html', {'held_assets': held_assets})

@login_required
def get_shipping_addresses(request):
    """AJAX endpoint to get user's shipping addresses"""
    addresses = request.user.shipping_addresses.all()
    
    addresses_data = []
    for address in addresses:
        addresses_data.append({
            'id': str(address.id),
            'full_name': address.full_name,
            'address_line_1': address.address_line_1,
            'city': address.city,
            'is_default': address.is_default
        })
    
    return JsonResponse({
        'success': True,
        'addresses': addresses_data
    })

@require_http_methods(["POST"])
@login_required
def liquidate_asset(request, order_id):
    """AJAX endpoint to liquidate held assets"""
    try:
        order = get_object_or_404(Order, id=order_id, user=request.user)
        
        if order.fulfillment_type != 'hold_asset' or order.status != 'paid':
            return JsonResponse({'success': False, 'error': 'Order cannot be liquidated'})
        
        address_id = request.POST.get('shipping_address_id')
        if not address_id:
            return JsonResponse({'success': False, 'error': 'Shipping address is required'})
        
        shipping_address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
        
        if order.liquidate_assets(shipping_address):
            return JsonResponse({
                'success': True,
                'message': 'Asset liquidated successfully. Your order will be shipped soon.'
            })
        
        return JsonResponse({'success': False, 'error': 'Failed to liquidate asset'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

@login_required
def shipping_addresses(request):
    """Manage shipping addresses"""
    addresses = request.user.shipping_addresses.all()
    return render(request, 'orders/shipping_addresses.html', {'addresses': addresses})

@require_http_methods(["POST"])
@login_required
def add_shipping_address(request):
    """AJAX endpoint to add shipping address"""
    try:
        address = ShippingAddress.objects.create(
            user=request.user,
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone'),
            address_line_1=request.POST.get('address_line_1'),
            address_line_2=request.POST.get('address_line_2', ''),
            city=request.POST.get('city'),
            state=request.POST.get('state'),
            postal_code=request.POST.get('postal_code'),
            country=request.POST.get('country', 'Nigeria'),
            is_default=request.POST.get('is_default') == 'true'
        )
        
        return JsonResponse({
            'success': True,
            'address': {
                'id': str(address.id),
                'full_name': address.full_name,
                'full_address': address.full_address,
                'is_default': address.is_default,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to add address'})

@require_http_methods(["GET"])
@login_required
def get_shipping_address(request, address_id):
    """AJAX endpoint to get shipping address data"""
    try:
        address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
        
        return JsonResponse({
            'success': True,
            'address': {
                'id': str(address.id),
                'first_name': address.first_name,
                'last_name': address.last_name,
                'email': address.email,
                'phone': address.phone,
                'address_line_1': address.address_line_1,
                'address_line_2': address.address_line_2,
                'city': address.city,
                'state': address.state,
                'postal_code': address.postal_code,
                'country': address.country,
                'is_default': address.is_default,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to get address'})

@require_http_methods(["POST"])
@login_required
def edit_shipping_address(request, address_id):
    """AJAX endpoint to edit shipping address"""
    try:
        address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
        
        # Update address fields
        address.first_name = request.POST.get('first_name', '').strip()
        address.last_name = request.POST.get('last_name', '').strip()
        address.email = request.POST.get('email', '').strip()
        address.phone = request.POST.get('phone', '').strip()
        address.address_line_1 = request.POST.get('address_line_1', '').strip()
        address.address_line_2 = request.POST.get('address_line_2', '').strip()
        address.city = request.POST.get('city', '').strip()
        address.state = request.POST.get('state', '').strip()
        address.postal_code = request.POST.get('postal_code', '').strip()
        address.country = request.POST.get('country', 'Nigeria').strip()
        
        # Handle default setting
        is_default = request.POST.get('is_default') == 'true'
        if is_default and not address.is_default:
            # Remove default from other addresses
            ShippingAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)
            address.is_default = True
        elif not is_default:
            address.is_default = False
        
        # Validate required fields
        required_fields = {
            'first_name': address.first_name,
            'last_name': address.last_name,
            'address_line_1': address.address_line_1,
            'city': address.city,
            'state': address.state,
            'country': address.country,
        }
        
        missing_fields = [field for field, value in required_fields.items() if not value]
        if missing_fields:
            return JsonResponse({
                'success': False, 
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            })
        
        address.save()
        
        return JsonResponse({
            'success': True,
            'address': {
                'id': str(address.id),
                'full_name': address.full_name,
                'full_address': address.full_address,
                'is_default': address.is_default,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to update address'})

@require_http_methods(["POST"])
@login_required
def set_default_address(request, address_id):
    """AJAX endpoint to set address as default"""
    try:
        address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
        
        # Remove default from all other addresses
        ShippingAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)
        
        # Set this address as default
        address.is_default = True
        address.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to set default address'})

# Update the existing add_shipping_address function to handle default setting properly
@require_http_methods(["POST"])
@login_required
def add_shipping_address(request):
    """AJAX endpoint to add shipping address"""
    try:
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        address_line_1 = request.POST.get('address_line_1', '').strip()
        address_line_2 = request.POST.get('address_line_2', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        postal_code = request.POST.get('postal_code', '').strip()
        country = request.POST.get('country', 'Nigeria').strip()
        is_default = request.POST.get('is_default') == 'true'
        
        # Validate required fields
        required_fields = {
            'first_name': first_name,
            'last_name': last_name,
            'address_line_1': address_line_1,
            'city': city,
            'state': state,
            'country': country,
        }
        
        missing_fields = [field for field, value in required_fields.items() if not value]
        if missing_fields:
            return JsonResponse({
                'success': False, 
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            })
        
        # If this is being set as default, remove default from other addresses
        if is_default:
            ShippingAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)
        # If user has no addresses yet, make this the default
        elif not ShippingAddress.objects.filter(user=request.user).exists():
            is_default = True
        
        address = ShippingAddress.objects.create(
            user=request.user,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            is_default=is_default
        )
        
        return JsonResponse({
            'success': True,
            'address': {
                'id': str(address.id),
                'full_name': address.full_name,
                'full_address': address.full_address,
                'is_default': address.is_default,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to add address'})

@require_http_methods(["POST"])
@login_required
def delete_shipping_address(request, address_id):
    """AJAX endpoint to delete shipping address"""
    try:
        address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
        address.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Failed to delete address'})

@require_http_methods(["POST"])
@login_required
def cancel_order(request, order_id):
    """AJAX endpoint to cancel order"""
    try:
        order = get_object_or_404(Order, id=order_id, user=request.user)
        
        # Only allow cancellation of pending orders
        if order.status != 'pending':
            return JsonResponse({
                'success': False, 
                'error': 'Only pending orders can be cancelled'
            })
        
        # Update order status
        order.status = 'cancelled'
        order.cancelled_at = timezone.now()
        order.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Order cancelled successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'error': 'An error occurred while cancelling the order'
        })