from django.db import models
from django.contrib.auth.models import User
from core.models import BaseModel
from orders.models import Order
from django.utils import timezone

class Payment(BaseModel):
    """Generic payment model - platform agnostic but focused on Paystack"""
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('paystack', 'Paystack'),
        # Future payment methods can be added here
    ]
    
    # Payment identification
    payment_reference = models.CharField(max_length=100, unique=True, help_text="Unique payment reference")
    external_transaction_id = models.CharField(max_length=100, blank=True, help_text="External gateway transaction ID")
    
    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    
    # Payment details
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount in base currency")
    currency = models.CharField(max_length=3, default='NGN')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paystack')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Payment metadata
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    
    # Gateway-specific data (JSON for flexibility)
    gateway_data = models.JSONField(default=dict, blank=True, help_text="Gateway-specific payment data")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
        ]
    
    def __str__(self):
        return f"Payment {self.payment_reference} - {self.user.email} - {self.status}"
    
    @property
    def amount_in_kobo(self):
        """Convert amount to kobo (Paystack uses kobo)"""
        return int(self.amount * 100)
    
    @property
    def is_successful(self):
        """Check if payment was successful"""
        return self.status == 'success'
    
    @property
    def is_pending(self):
        """Check if payment is pending"""
        return self.status in ['pending', 'processing']
    
    @property
    def is_failed(self):
        """Check if payment failed"""
        return self.status in ['failed', 'cancelled']
    
    def mark_as_processing(self):
        """Mark payment as processing"""
        self.status = 'processing'
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_at'])
    
    def mark_as_successful(self, external_transaction_id=None, additional_data=None):
        """Mark payment as successful"""
        self.status = 'success'
        if external_transaction_id:
            self.external_transaction_id = external_transaction_id
        if additional_data:
            self.gateway_data.update(additional_data)
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'external_transaction_id', 'gateway_data', 'completed_at'])
        
        # Update order status
        self.order.status = 'paid'
        self.order.paid_at = timezone.now()
        self.order.payment_reference = self.payment_reference
        self.order.save()
    
    def mark_as_failed(self, error_message=None, error_code=None):
        """Mark payment as failed"""
        self.status = 'failed'
        if error_message:
            self.error_message = error_message
        if error_code:
            self.error_code = error_code
        self.save(update_fields=['status', 'error_message', 'error_code'])
    
    def mark_as_cancelled(self):
        """Mark payment as cancelled"""
        self.status = 'cancelled'
        self.save(update_fields=['status'])
    
    # Convenience methods for Paystack data
    @property
    def paystack_authorization_url(self):
        """Get Paystack authorization URL from gateway data"""
        return self.gateway_data.get('authorization_url', '')
    
    @property
    def paystack_access_code(self):
        """Get Paystack access code from gateway data"""
        return self.gateway_data.get('access_code', '')

class PaymentWebhook(BaseModel):
    """Model to store webhook data for debugging and audit"""
    
    webhook_id = models.CharField(max_length=100, unique=True)
    gateway_name = models.CharField(max_length=50, help_text="Name of the payment gateway")
    event_type = models.CharField(max_length=100)
    payment_reference = models.CharField(max_length=100)
    webhook_data = models.JSONField()
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.gateway_name} webhook {self.webhook_id} - {self.event_type}"
    
    def mark_as_processed(self):
        """Mark webhook as processed"""
        self.processed = True
        self.processed_at = timezone.now()
        self.save(update_fields=['processed', 'processed_at'])
