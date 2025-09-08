import requests
import json
import hashlib
import hmac
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from core.models import SiteConfiguration
from .models import Payment, PaymentWebhook

class PaystackGateway:
    """Paystack payment gateway implementation"""
    
    def __init__(self):
        self.config = SiteConfiguration.get_config()
        self.secret_key = self.config.paystack_secret_key
        self.public_key = self.config.paystack_public_key
        self.base_url = "https://api.paystack.co"
        
        if not self.secret_key or not self.public_key:
            raise ValueError("Paystack keys not configured in SiteConfiguration")
    
    def initialize_payment(self, payment: Payment) -> dict:
        """Initialize payment with Paystack"""
        try:
            url = f"{self.base_url}/transaction/initialize"
            
            payload = {
                'email': payment.customer_email,
                'amount': payment.amount_in_kobo,
                'reference': payment.payment_reference,
                'currency': payment.currency,
                'callback_url': f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/payments/verify/{payment.payment_reference}/",
                'metadata': {
                    'order_id': str(payment.order.id),
                    'user_id': payment.user.id,
                    'fulfillment_type': payment.order.fulfillment_type,
                }
            }
            
            # Add customer name if available
            if payment.customer_name:
                payload['metadata']['customer_name'] = payment.customer_name
            
            # Add phone if available
            if payment.customer_phone:
                payload['metadata']['customer_phone'] = payment.customer_phone
            
            headers = {
                'Authorization': f'Bearer {self.secret_key}',
                'Content-Type': 'application/json',
            }
            
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status']:
                # Update payment with Paystack data
                payment.gateway_data.update({
                    'authorization_url': data['data']['authorization_url'],
                    'access_code': data['data']['access_code'],
                    'paystack_data': data['data']
                })
                payment.save()
                
                return {
                    'success': True,
                    'authorization_url': data['data']['authorization_url'],
                    'access_code': data['data']['access_code'],
                    'reference': data['data']['reference']
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Payment initialization failed')
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Unexpected error: {str(e)}'
            }
    
    def verify_payment(self, payment: Payment) -> dict:
        """Verify payment with Paystack"""
        try:
            url = f"{self.base_url}/transaction/verify/{payment.payment_reference}"
            
            headers = {
                'Authorization': f'Bearer {self.secret_key}',
                'Content-Type': 'application/json',
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status']:
                transaction_data = data['data']
                
                # Check if payment is already processed
                if payment.is_successful:
                    return {
                        'success': True,
                        'message': 'Payment already verified',
                        'payment': payment
                    }
                
                # Verify amount matches
                if transaction_data['amount'] != payment.amount_in_kobo:
                    payment.mark_as_failed(
                        error_message=f"Amount mismatch. Expected: {payment.amount_in_kobo}, Got: {transaction_data['amount']}",
                        error_code="AMOUNT_MISMATCH"
                    )
                    return {
                        'success': False,
                        'message': 'Amount mismatch'
                    }
                
                # Check transaction status
                if transaction_data['status'] == 'success':
                    # Mark payment as successful
                    payment.mark_as_successful(
                        external_transaction_id=transaction_data['id'],
                        additional_data={'paystack_data': transaction_data}
                    )
                    
                    return {
                        'success': True,
                        'message': 'Payment verified successfully',
                        'payment': payment,
                        'transaction_data': transaction_data
                    }
                else:
                    # Mark payment as failed
                    payment.mark_as_failed(
                        error_message=f"Transaction failed: {transaction_data.get('gateway_response', 'Unknown error')}",
                        error_code=transaction_data.get('status', 'FAILED')
                    )
                    
                    return {
                        'success': False,
                        'message': f"Transaction failed: {transaction_data.get('gateway_response', 'Unknown error')}"
                    }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Payment verification failed')
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Unexpected error: {str(e)}'
            }
    
    def process_webhook(self, payload: str, signature: str) -> dict:
        """Process Paystack webhook"""
        try:
            # Verify webhook signature
            if not self._verify_webhook_signature(payload, signature):
                return {
                    'success': False,
                    'message': 'Invalid webhook signature'
                }
            
            # Parse webhook data
            webhook_data = json.loads(payload)
            event_type = webhook_data.get('event')
            data = webhook_data.get('data', {})
            
            # Store webhook for audit
            webhook = PaymentWebhook.objects.create(
                webhook_id=webhook_data.get('id', ''),
                gateway_name='paystack',
                event_type=event_type,
                payment_reference=data.get('reference', ''),
                webhook_data=webhook_data
            )
            
            # Process based on event type
            if event_type == 'charge.success':
                return self._handle_successful_charge(data, webhook)
            elif event_type == 'charge.failed':
                return self._handle_failed_charge(data, webhook)
            elif event_type == 'transfer.success':
                return self._handle_successful_transfer(data, webhook)
            else:
                # Mark as processed for other event types
                webhook.mark_as_processed()
                
                return {
                    'success': True,
                    'message': f'Webhook processed: {event_type}'
                }
                
        except json.JSONDecodeError:
            return {
                'success': False,
                'message': 'Invalid JSON payload'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Webhook processing error: {str(e)}'
            }
    
    def _verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature from Paystack"""
        try:
            # Create HMAC SHA512 hash
            computed_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            return hmac.compare_digest(computed_signature, signature)
        except Exception:
            return False
    
    def _handle_successful_charge(self, data: dict, webhook) -> dict:
        """Handle successful charge webhook"""
        try:
            reference = data.get('reference')
            payment = Payment.objects.get(payment_reference=reference)
            
            # Mark payment as successful
            payment.mark_as_successful(
                external_transaction_id=data.get('id'),
                additional_data={'paystack_data': data}
            )
            
            # Mark webhook as processed
            webhook.mark_as_processed()
            
            return {
                'success': True,
                'message': 'Payment marked as successful via webhook'
            }
            
        except Payment.DoesNotExist:
            webhook.mark_as_processed()
            
            return {
                'success': False,
                'message': 'Payment not found for webhook'
            }
    
    def _handle_failed_charge(self, data: dict, webhook) -> dict:
        """Handle failed charge webhook"""
        try:
            reference = data.get('reference')
            payment = Payment.objects.get(payment_reference=reference)
            
            # Mark payment as failed
            payment.mark_as_failed(
                error_message=data.get('gateway_response', 'Payment failed'),
                error_code=data.get('status', 'FAILED')
            )
            
            # Mark webhook as processed
            webhook.mark_as_processed()
            
            return {
                'success': True,
                'message': 'Payment marked as failed via webhook'
            }
            
        except Payment.DoesNotExist:
            webhook.mark_as_processed()
            
            return {
                'success': False,
                'message': 'Payment not found for webhook'
            }
    
    def _handle_successful_transfer(self, data: dict, webhook) -> dict:
        """Handle successful transfer webhook (for refunds)"""
        # Mark webhook as processed
        webhook.mark_as_processed()
        
        return {
            'success': True,
            'message': 'Transfer webhook processed'
        } 