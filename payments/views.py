import json
import uuid
import hmac
import hashlib
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from orders.models import Order, OrderItem, Cart, ShippingAddress
from .models import Payment
from .services import PaymentService

@login_required
@require_http_methods(["POST"])
def initiate_payment(request):
    """Initiate payment process"""
    try:
        data = json.loads(request.body)
        fulfillment_type = data.get('fulfillment_type')
        shipping_address_id = data.get('shipping_address_id')
        shipping_address_data = data.get('shipping_address')
        customer_notes = data.get('customer_notes', '')
        
        # Validate fulfillment type
        if fulfillment_type not in ['hold_asset', 'deliver']:
            return JsonResponse({
                'success': False,
                'message': 'Invalid fulfillment type'
            }, status=400)
        
        shipping_address = None
        
        # Handle shipping address for delivery orders
        if fulfillment_type == 'deliver':
            if shipping_address_id:
                # Using existing address
                try:
                    shipping_address = ShippingAddress.objects.get(
                        id=shipping_address_id,
                        user=request.user
                    )
                except ShippingAddress.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Shipping address not found'
                    }, status=400)
            elif shipping_address_data:
                # Creating new address
                required_fields = ['first_name', 'last_name', 'address_line_1', 'city', 'state', 'country']
                missing_fields = [field for field in required_fields if not shipping_address_data.get(field)]
                
                if missing_fields:
                    return JsonResponse({
                        'success': False,
                        'message': f'Missing required address fields: {", ".join(missing_fields)}'
                    }, status=400)
                
                try:
                    shipping_address = ShippingAddress.objects.create(
                        user=request.user,
                        first_name=shipping_address_data.get('first_name'),
                        last_name=shipping_address_data.get('last_name'),
                        email=shipping_address_data.get('email', ''),
                        phone=shipping_address_data.get('phone', ''),
                        address_line_1=shipping_address_data.get('address_line_1'),
                        address_line_2=shipping_address_data.get('address_line_2', ''),
                        city=shipping_address_data.get('city'),
                        state=shipping_address_data.get('state'),
                        postal_code=shipping_address_data.get('postal_code', ''),
                        country=shipping_address_data.get('country'),
                        is_default=shipping_address_data.get('is_default', False)
                    )
                except Exception as e:
                    return JsonResponse({
                        'success': False,
                        'message': f'Error creating shipping address: {str(e)}'
                    }, status=400)
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Shipping address is required for delivery orders'
                }, status=400)
        
        with transaction.atomic():
            # Get cart and items
            try:
                cart = Cart.objects.get(user=request.user)
                cart_items = cart.items.all()
                
                if not cart_items.exists():
                    return JsonResponse({
                        'success': False,
                        'message': 'Cart is empty'
                    }, status=400)
            except Cart.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Cart not found'
                }, status=400)
            
            # Check stock availability for all items
            for cart_item in cart_items:
                if not cart_item.product.can_purchase(cart_item.quantity):
                    return JsonResponse({
                        'success': False,
                        'message': f'{cart_item.product.title} is out of stock or has insufficient quantity'
                    }, status=400)
            
            # Create order
            order = Order.objects.create(
                user=request.user,
                fulfillment_type=fulfillment_type,
                shipping_address=shipping_address,
                customer_notes=customer_notes
            )
            
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
    """
    Paystack webhook handler to process payment events.
    """
    # Verify the request is from Paystack
    paystack_sk = settings.PAYSTACK_SECRET_KEY
    signature = request.headers.get('x-paystack-signature')
    
    if not signature:
        return HttpResponse(status=400)

    try:
        body = request.body.decode('utf-8')
        hash = hmac.new(paystack_sk.encode('utf-8'), body.encode('utf-8'), hashlib.sha512).hexdigest()
        
        if hash != signature:
            return HttpResponse(status=400)
            
    except Exception as e:
        # Log the error for debugging
        print(f"Webhook signature verification failed: {e}")
        return HttpResponse(status=400)

    try:
        payload = json.loads(body)
        event = payload.get('event')

        if event == 'charge.success':
            data = payload.get('data')
            reference = data.get('reference')
            
            # Find the corresponding payment and order
            try:
                payment = get_object_or_404(Payment, reference=reference)
                order = payment.order

                # Update order and payment status if payment was successful
                if data.get('status') == 'success':
                    order.status = 'paid'
                    order.paid_at = timezone.now() # Make sure to import timezone
                    order.save()

                    payment.status = 'success'
                    payment.raw_response = data # Store the full response
                    payment.save()
                    
            except (Payment.DoesNotExist, Order.DoesNotExist) as e:
                 return HttpResponse(status=404) # Not found

        return HttpResponse(status=200)

    except json.JSONDecodeError:
        return HttpResponse(status=400)
    except Exception as e:
        return HttpResponse(status=500)

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
