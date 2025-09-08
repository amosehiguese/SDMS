from .models import Payment
from .gateways import PaystackGateway

class PaymentService:
    """Payment service that works with Paystack (easily extensible for other gateways)"""
    
    def __init__(self, gateway_name: str = 'paystack'):
        self.gateway_name = gateway_name
        
        if gateway_name == 'paystack':
            self.gateway = PaystackGateway()
        else:
            raise ValueError(f"Unsupported gateway: {gateway_name}")
    
    def initialize_payment(self, payment: Payment) -> dict:
        """Initialize payment using the configured gateway"""
        try:
            # Validate payment before initialization
            validation_result = self._validate_payment(payment)
            if not validation_result['success']:
                return validation_result
            
            # Initialize payment with gateway
            result = self.gateway.initialize_payment(payment)
            
            if result['success']:
                # Update payment status to processing
                payment.mark_as_processing()
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Payment initialization error: {str(e)}'
            }
    
    def verify_payment(self, payment: Payment) -> dict:
        """Verify payment using the configured gateway"""
        try:
            result = self.gateway.verify_payment(payment)
            return result
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Payment verification error: {str(e)}'
            }
    
    def process_webhook(self, payload: str, signature: str) -> dict:
        """Process webhook from the configured gateway"""
        try:
            result = self.gateway.process_webhook(payload, signature)
            return result
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Webhook processing error: {str(e)}'
            }
    
    def get_payment_status(self, payment: Payment) -> dict:
        """Get current payment status"""
        try:
            return {
                'success': True,
                'status': payment.status,
                'amount': str(payment.amount),
                'currency': payment.currency,
                'created_at': payment.created_at.isoformat(),
                'completed_at': payment.completed_at.isoformat() if payment.completed_at else None,
                'gateway_name': self.gateway_name,
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Error getting payment status: {str(e)}'
            }
    
    def _validate_payment(self, payment: Payment) -> dict:
        """Validate payment before processing"""
        if not payment.user:
            return {
                'success': False,
                'message': 'Payment must have a valid user'
            }
        
        if not payment.order:
            return {
                'success': False,
                'message': 'Payment must have a valid order'
            }
        
        if payment.amount <= 0:
            return {
                'success': False,
                'message': 'Payment amount must be greater than zero'
            }
        
        if not payment.customer_email:
            return {
                'success': False,
                'message': 'Customer email is required'
            }
        
        return {'success': True}


def get_payment_service(gateway_name: str = 'paystack') -> PaymentService:
    """Get a payment service instance for the specified gateway"""
    return PaymentService(gateway_name)

def initialize_payment(payment: Payment, gateway_name: str = 'paystack') -> dict:
    """Initialize payment with the specified gateway"""
    service = PaymentService(gateway_name)
    return service.initialize_payment(payment)

def verify_payment(payment: Payment, gateway_name: str = 'paystack') -> dict:
    """Verify payment with the specified gateway"""
    service = PaymentService(gateway_name)
    return service.verify_payment(payment)

def process_webhook(payload: str, signature: str, gateway_name: str = 'paystack') -> dict:
    """Process webhook from the specified gateway"""
    service = PaymentService(gateway_name)
    return service.process_webhook(payload, signature)
