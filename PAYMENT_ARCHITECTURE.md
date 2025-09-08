# Flexible Payment Architecture

This document outlines the new, flexible payment architecture that separates concerns and makes the system extensible for multiple payment gateways.

## 🏗️ **New Architecture Overview**

The payment system has been refactored to follow better separation of concerns:

```
payments/
├── models.py          # Generic payment models + gateway-specific models
├── gateways.py        # Payment gateway interface and implementations
├── services.py        # Generic payment service layer
├── views.py           # Payment views using the service layer
├── urls.py            # URL routing for multiple gateways
├── admin.py           # Admin interface for all models
└── templates/         # Payment templates
```

## 🔧 **Key Design Principles**

### 1. **Separation of Concerns**
- **Payment Model**: Generic, platform-agnostic payment tracking
- **Gateway Models**: Handle gateway-specific data separately
- **Service Layer**: Abstract payment processing logic
- **Gateway Interface**: Standardized gateway implementations

### 2. **Extensibility**
- Easy to add new payment gateways
- Gateway-specific data stored separately
- Common payment operations abstracted
- Plugin-like architecture for gateways

### 3. **Flexibility**
- Support for multiple payment methods
- Gateway-agnostic payment processing
- Easy switching between gateways
- Future-proof for new payment technologies

## 🗄️ **Database Models**

### **Core Payment Model** (`Payment`)
```python
class Payment(BaseModel):
    # Generic fields - work with any gateway
    payment_reference = models.CharField(max_length=100, unique=True)
    external_transaction_id = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES)
    
    # Customer metadata
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    
    # Timestamps and error handling
    initiated_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    
    # Flexible metadata storage
    metadata = models.JSONField(default=dict, blank=True)
```

### **Gateway-Specific Models**
```python
class PaystackPaymentData(PaymentGatewayData):
    # Paystack-specific fields
    access_code = models.CharField(max_length=100, blank=True)
    authorization_url = models.URLField(blank=True)
    customer_code = models.CharField(max_length=100, blank=True)

class StripePaymentData(PaymentGatewayData):
    # Stripe-specific fields
    payment_intent_id = models.CharField(max_length=100, blank=True)
    client_secret = models.CharField(max_length=200, blank=True)

class PayPalPaymentData(PaymentGatewayData):
    # PayPal-specific fields
    paypal_order_id = models.CharField(max_length=100, blank=True)
    approval_url = models.URLField(blank=True)
```

### **Supporting Models**
- **PaymentWebhook**: Webhook audit trail
- **PaymentRefund**: Refund tracking
- **PaymentGatewayData**: Abstract base for gateway data

## 🔌 **Payment Gateway Interface**

### **Abstract Base Class**
```python
class PaymentGateway(ABC):
    @abstractmethod
    def get_gateway_name(self) -> str:
        pass
    
    @abstractmethod
    def initialize_payment(self, payment: Payment) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def verify_payment(self, payment: Payment) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def process_webhook(self, payload: str, signature: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def refund_payment(self, payment: Payment, amount: Decimal, reason: str) -> Dict[str, Any]:
        pass
```

### **Gateway Implementations**
- **PaystackGateway**: Full Paystack integration
- **StripeGateway**: Placeholder for Stripe (ready for implementation)
- **PayPalGateway**: Placeholder for PayPal (ready for implementation)

## 🚀 **Service Layer**

### **Generic Payment Service**
```python
class PaymentService:
    def __init__(self, gateway_name: str = 'paystack'):
        self.gateway_name = gateway_name
        self.config = self._get_gateway_config()
        self.gateway = PaymentGatewayFactory.create_gateway(gateway_name, self.config)
    
    def initialize_payment(self, payment: Payment) -> dict:
        # Validate payment
        # Initialize with gateway
        # Handle response
    
    def verify_payment(self, payment: Payment) -> dict:
        # Verify with gateway
        # Update payment status
    
    def process_webhook(self, payload: str, signature: str) -> dict:
        # Process webhook
        # Update payment status
```

### **Gateway Factory**
```python
class PaymentGatewayFactory:
    @staticmethod
    def create_gateway(gateway_name: str, config: Dict[str, Any]) -> PaymentGateway:
        gateways = {
            'paystack': PaystackGateway,
            'stripe': StripeGateway,
        }
        return gateways[gateway_name](config)
```

## 🔄 **Payment Flow**

### **1. Payment Initiation**
```
User → Checkout → Select Payment Method → Create Payment Record → Initialize with Gateway → Redirect to Gateway
```

### **2. Payment Processing**
```
Gateway → Process Payment → Send Webhook → Update Payment Status → Update Order Status
```

### **3. Payment Verification**
```
User → Return to Site → Verify Payment → Update Status → Show Result
```

## 🎯 **Benefits of New Architecture**

### **1. Flexibility**
- Easy to add new payment gateways
- Gateway-specific data stored separately
- Common operations abstracted
- Payment method switching

### **2. Maintainability**
- Clear separation of concerns
- Easy to test individual components
- Consistent interface across gateways
- Reduced code duplication

### **3. Scalability**
- Support for multiple gateways
- Easy to handle different currencies
- Future-proof for new payment methods
- Better error handling

### **4. Security**
- Gateway-specific signature verification
- Secure webhook processing
- Audit trail for all operations
- Input validation at multiple levels

## 🚀 **Adding New Payment Gateways**

### **Step 1: Create Gateway Class**
```python
class NewGateway(PaymentGateway):
    def get_gateway_name(self) -> str:
        return 'new_gateway'
    
    def initialize_payment(self, payment: Payment) -> Dict[str, Any]:
        # Implement payment initialization
        pass
    
    def verify_payment(self, payment: Payment) -> Dict[str, Any]:
        # Implement payment verification
        pass
    
    def process_webhook(self, payload: str, signature: str) -> Dict[str, Any]:
        # Implement webhook processing
        pass
    
    def refund_payment(self, payment: Payment, amount: Decimal, reason: str) -> Dict[str, Any]:
        # Implement refund processing
        pass
```

### **Step 2: Create Gateway Data Model**
```python
class NewGatewayPaymentData(PaymentGatewayData):
    gateway_name = 'new_gateway'
    
    # Gateway-specific fields
    custom_field_1 = models.CharField(max_length=100, blank=True)
    custom_field_2 = models.URLField(blank=True)
```

### **Step 3: Add to Factory**
```python
class PaymentGatewayFactory:
    @staticmethod
    def create_gateway(gateway_name: str, config: Dict[str, Any]) -> PaymentGateway:
        gateways = {
            'paystack': PaystackGateway,
            'stripe': StripeGateway,
            'new_gateway': NewGateway,  # Add new gateway
        }
        return gateways[gateway_name](config)
```

### **Step 4: Add Configuration**
```python
def _get_gateway_config(self) -> dict:
    config = SiteConfiguration.get_config()
    
    if self.gateway_name == 'new_gateway':
        return {
            'new_gateway_secret_key': getattr(config, 'new_gateway_secret_key', ''),
            'new_gateway_public_key': getattr(config, 'new_gateway_public_key', ''),
        }
```

## 🔧 **Configuration**

### **Environment Variables**
```bash
PAYSTACK_SECRET_KEY=your_paystack_secret
PAYSTACK_PUBLIC_KEY=your_paystack_public
STRIPE_SECRET_KEY=your_stripe_secret
STRIPE_PUBLIC_KEY=your_stripe_public
SITE_URL=http://localhost:8000
```

### **Site Configuration**
- Paystack keys
- Stripe keys (when implemented)
- Tax rates
- Shipping costs
- Gateway preferences

## 🧪 **Testing**

### **Test Scenarios**
1. **Payment Initialization**: Test with different gateways
2. **Payment Verification**: Test verification flows
3. **Webhook Processing**: Test webhook handling
4. **Error Handling**: Test various error scenarios
5. **Gateway Switching**: Test different payment methods

### **Test Data**
- Use test keys for all gateways
- Test webhook signatures
- Verify amount calculations
- Test error conditions

## 🔍 **Monitoring & Debugging**

### **Admin Interface**
- Payment status monitoring
- Gateway data review
- Webhook processing status
- Error tracking

### **Logging**
- Payment flow tracking
- Gateway interactions
- Webhook processing
- Error logging

## 🚨 **Error Handling**

### **Common Errors**
1. **Gateway Errors**: API failures, network issues
2. **Validation Errors**: Invalid data, missing fields
3. **Webhook Errors**: Invalid signatures, processing failures
4. **Configuration Errors**: Missing keys, invalid settings

### **Error Recovery**
- Automatic retry mechanisms
- User-friendly error messages
- Admin notification system
- Detailed error logging

## 🔄 **Migration from Old System**

### **Data Migration**
- Existing payments will continue to work
- New payments use the new architecture
- Gradual migration possible

### **Code Updates**
- Update imports to use new services
- Replace direct PaystackService calls
- Update webhook handling

## 📚 **API Documentation**

### **Payment Endpoints**
- `POST /payments/initiate/` - Initialize payment
- `GET /payments/verify/{reference}/` - Verify payment
- `GET /payments/status/{reference}/` - Get payment status

### **Webhook Endpoints**
- `POST /payments/webhook/paystack/` - Paystack webhooks
- `POST /payments/webhook/stripe/` - Stripe webhooks

## 🛠️ **Troubleshooting**

### **Common Issues**
1. **Gateway Not Working**: Check configuration and keys
2. **Webhook Failures**: Verify signatures and endpoints
3. **Payment Verification Issues**: Check gateway responses
4. **Configuration Problems**: Verify environment variables

### **Debug Steps**
1. Check Django logs for errors
2. Verify gateway configuration
3. Test webhook endpoints
4. Review payment model data

---

**Note**: This new architecture provides a solid foundation for handling multiple payment gateways while maintaining clean separation of concerns and extensibility for future payment methods. 