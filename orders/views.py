from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse
from .models import Order, OrderItem, Cart, CartItem, ShippingAddress
from store.models import Product

@login_required
def cart_view(request):
    """Display shopping cart"""
    cart, created = Cart.objects.get_or_create(user=request.user)
    return render(request, 'orders/cart.html', {'cart': cart})

@require_http_methods(["POST"])
@login_required
def add_to_cart(request):
    """AJAX endpoint to add product to cart"""
    try:
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        if not product.can_purchase(quantity):
            return JsonResponse({
                'success': False, 
                'error': 'Product is out of stock or insufficient quantity available'
            })
        
        cart, created = Cart.objects.get_or_create(user=request.user)
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
        
        return JsonResponse({
            'success': True,
            'cart_total_items': cart.get_total_items(),
            'cart_subtotal': str(cart.get_subtotal()),
            'message': f'{product.title} added to cart'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

@require_http_methods(["POST"])
@login_required
def update_cart_item(request):
    """AJAX endpoint to update cart item quantity"""
    try:
        item_id = request.POST.get('item_id')
        quantity = int(request.POST.get('quantity', 1))
        
        cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        
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
@login_required
def remove_from_cart(request):
    """AJAX endpoint to remove item from cart"""
    try:
        item_id = request.POST.get('item_id')
        cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        cart = cart_item.cart
        cart_item.delete()
        
        return JsonResponse({
            'success': True,
            'cart_total_items': cart.get_total_items(),
            'cart_subtotal': str(cart.get_subtotal())
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

@login_required
def checkout(request):
    """Checkout page"""
    cart = get_object_or_404(Cart, user=request.user)
    
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
        cart = get_object_or_404(Cart, user=request.user)
        
        if not cart.items.exists():
            return JsonResponse({'success': False, 'error': 'Cart is empty'})
        
        fulfillment_type = request.POST.get('fulfillment_type')
        if fulfillment_type not in ['hold_asset', 'deliver']:
            return JsonResponse({'success': False, 'error': 'Invalid fulfillment type'})
        
        # For delivery orders, validate shipping address
        shipping_address = None
        if fulfillment_type == 'deliver':
            address_id = request.POST.get('shipping_address_id')
            if not address_id:
                return JsonResponse({'success': False, 'error': 'Shipping address is required for delivery'})
            shipping_address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)
        
        # Create order
        order = Order.objects.create(
            user=request.user,
            fulfillment_type=fulfillment_type,
            shipping_address=shipping_address,
            customer_notes=request.POST.get('notes', '')
        )
        
        # Create order items
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
        
        # Calculate totals
        order.calculate_totals()
        
        # Clear cart
        cart.clear()
        
        return JsonResponse({
            'success': True,
            'order_id': str(order.id),
            'redirect_url': reverse('payments:paystack_pay', args=[order.id])
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred while creating order'})

@login_required
def order_detail(request, order_id):
    """Order detail page"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/order_detail.html', {'order': order})

@login_required
def order_history(request):
    """User's order history"""
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product')
    return render(request, 'orders/order_history.html', {'orders': orders})

@login_required
def held_assets(request):
    """User's held assets"""
    held_orders = Order.objects.filter(
        user=request.user,
        fulfillment_type='hold_asset',
        status='paid'
    ).prefetch_related('items__product')
    
    return render(request, 'orders/held_assets.html', {'held_orders': held_orders})

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