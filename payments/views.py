import json
import uuid
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from orders.models import Order, OrderItem, Cart, CartItem, ShippingAddress
from .models import Payment
from .services import PaymentService

@login_required
def checkout(request):
    """Checkout page where user can review cart and initiate payment"""
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.items.all()
        
        if not cart_items.exists():
            messages.warning(request, "Your cart is empty")
            return redirect('store:cart')
        
        # Get user's shipping addresses
        shipping_addresses = ShippingAddress.objects.filter(user=request.user)
        
        # Calculate totals
        subtotal = cart.get_subtotal()
        
        # Get site configuration for shipping and tax
        from core.models import SiteConfiguration
        config = SiteConfiguration.get_config()
        
        # Calculate shipping cost
        shipping_cost = Decimal('0.00')
        if subtotal < config.free_shipping_threshold:
            shipping_cost = config.default_shipping_cost
        
        # Calculate tax
        tax_rate = getattr(config, 'tax_rate', Decimal('0.00'))
        tax_amount = subtotal * tax_rate
        
        total = subtotal + shipping_cost + tax_amount
        
        context = {
            'cart_items': cart_items,
            'subtotal': subtotal,
            'shipping_cost': shipping_cost,
            'tax_amount': tax_amount,
            'total': total,
            'shipping_addresses': shipping_addresses,
            'paystack_public_key': config.paystack_public_key,
        }
        
        return render(request, 'payments/checkout.html', context)
        
    except Cart.DoesNotExist:
        messages.warning(request, "Your cart is empty")
        return redirect('store:cart')

@login_required
@require_http_methods(["POST"])
def initiate_payment(request):
    """Initiate payment process"""
    try:
        data = json.loads(request.body)
        fulfillment_type = data.get('fulfillment_type')
        shipping_address_id = data.get('shipping_address_id')
        customer_notes = data.get('customer_notes', '')
        
        # Validate fulfillment type
        if fulfillment_type not in ['hold_asset', 'deliver']:
            return JsonResponse({
                'success': False,
                'message': 'Invalid fulfillment type'
            }, status=400)
        
        # Validate shipping address for delivery orders
        if fulfillment_type == 'deliver' and not shipping_address_id:
            return JsonResponse({
                'success': False,
                'message': 'Shipping address is required for delivery orders'
            }, status=400)
        
        with transaction.atomic():
            # Get cart and items
            cart = Cart.objects.get(user=request.user)
            cart_items = cart.items.all()
            
            if not cart_items.exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Cart is empty'
                }, status=400)
            
            # Create order
            order = Order.objects.create(
                user=request.user,
                fulfillment_type=fulfillment_type,
                customer_notes=customer_notes
            )
            
            # Add shipping address if delivery
            if fulfillment_type == 'deliver' and shipping_address_id:
                try:
                    shipping_address = ShippingAddress.objects.get(
                        id=shipping_address_id,
                        user=request.user
                    )
                    order.shipping_address = shipping_address
                    order.save()
                except ShippingAddress.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Shipping address not found'
                    }, status=400)
            
            # Create order items
            for cart_item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.product.get_display_price()
                )
            
            # Calculate order totals
            order.calculate_totals()
            
            # Create payment record
            payment_reference = f"PAY_{uuid.uuid4().hex[:16].upper()}"
            payment = Payment.objects.create(
                payment_reference=payment_reference,
                user=request.user,
                order=order,
                amount=order.total,
                customer_email=request.user.email,
                customer_name=f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email
            )
            
            # Initialize payment with Paystack
            payment_service = PaymentService('paystack')
            result = payment_service.initialize_payment(payment)
            
            if result['success']:
                # Clear cart after successful order creation
                cart.clear()
                
                return JsonResponse({
                    'success': True,
                    'payment_reference': payment_reference,
                    'authorization_url': result.get('authorization_url', ''),
                    'order_id': str(order.id),
                    'message': 'Payment initiated successfully'
                })
            else:
                # Delete order if payment initialization fails
                order.delete()
                return JsonResponse({
                    'success': False,
                    'message': result['message']
                }, status=400)
                
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)

@login_required
def payment_verification(request, reference):
    """Verify payment after user returns from Paystack"""
    try:
        payment = get_object_or_404(Payment, payment_reference=reference, user=request.user)
        
        # Verify payment with Paystack
        payment_service = PaymentService('paystack')
        result = payment_service.verify_payment(payment)
        
        if result['success']:
            messages.success(request, 'Payment verified successfully!')
            return redirect('orders:order_detail', order_id=payment.order.id)
        else:
            messages.error(request, f'Payment verification failed: {result["message"]}')
            return redirect('orders:order_detail', order_id=payment.order.id)
            
    except Exception as e:
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('store:home')

@login_required
def payment_status(request, reference):
    """Get payment status via AJAX"""
    try:
        payment = get_object_or_404(Payment, payment_reference=reference, user=request.user)
        
        # Get payment service for Paystack
        payment_service = PaymentService('paystack')
        result = payment_service.get_payment_status(payment)
        
        if result['success']:
            return JsonResponse(result)
        else:
            return JsonResponse({
                'success': False,
                'message': result['message']
            }, status=400)
        
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Payment not found'
        }, status=404)

@csrf_exempt
def paystack_webhook(request):
    """Handle Paystack webhook notifications"""
    if request.method != 'POST':
        return HttpResponse(status=405)
    
    try:
        # Get webhook signature
        signature = request.headers.get('X-Paystack-Signature')
        if not signature:
            return HttpResponse('Missing signature', status=400)
        
        # Process webhook
        payment_service = PaymentService('paystack')
        result = payment_service.process_webhook(request.body.decode('utf-8'), signature)
        
        if result['success']:
            return HttpResponse('Webhook processed successfully', status=200)
        else:
            return HttpResponse(f'Webhook processing failed: {result["message"]}', status=400)
            
    except Exception as e:
        return HttpResponse(f'Webhook error: {str(e)}', status=500)

@login_required
def payment_history(request):
    """User's payment history"""
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'payments': payments
    }
    
    return render(request, 'payments/payment_history.html', context)

@login_required
def payment_detail(request, reference):
    """Payment detail view"""
    payment = get_object_or_404(Payment, payment_reference=reference, user=request.user)
    
    context = {
        'payment': payment
    }
    
    return render(request, 'payments/payment_detail.html', context)

def payment_success(request):
    """Payment success page"""
    return render(request, 'payments/payment_success.html')

def payment_failed(request):
    """Payment failed page"""
    return render(request, 'payments/payment_failed.html')
