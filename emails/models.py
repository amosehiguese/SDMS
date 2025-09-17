from django.db import models
from core.models import BaseModel

class EmailTemplate(BaseModel):
    """Configurable email templates"""
    EMAIL_TYPES = [
        # User emails
        ('welcome', 'Welcome Email'),
        ('order_confirmation', 'Order Confirmation'),
        ('order_shipped', 'Order Shipped'),
        ('order_delivered', 'Order Delivered'),
        ('receipt', 'Payment Receipt'),
        ('asset_liquidation', 'Asset Liquidation Request'),
        ('sell_item_submitted', 'Sell Item Submitted'),
        ('sell_item_approved', 'Sell Item Approved'),
        ('sell_item_rejected', 'Sell Item Rejected'),
        
        # Admin emails
        ('new_order_admin', 'New Order (Admin)'),
        ('new_user_admin', 'New User Registration (Admin)'),
        ('sell_item_review_admin', 'Sell Item Review Required (Admin)'),
        ('low_stock_admin', 'Low Stock Alert (Admin)'),
        ('payment_failed_admin', 'Payment Failed (Admin)'),
    ]
    
    RECIPIENT_TYPES = [
        ('user', 'User'),
        ('admin', 'Admin'),
    ]
    
    email_type = models.CharField(max_length=50, choices=EMAIL_TYPES, unique=True)
    recipient_type = models.CharField(max_length=10, choices=RECIPIENT_TYPES)
    subject = models.CharField(max_length=200, help_text="Use {variable} for dynamic content")
    template_path = models.CharField(max_length=200, help_text="Path to HTML template")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['email_type']
        
    def __str__(self):
        return f"{self.get_email_type_display()} - {self.get_recipient_type_display()}"

class EmailLog(BaseModel):
    """Log all sent emails for debugging and tracking"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    email_type = models.CharField(max_length=50)
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Context data for debugging
    context_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.email_type} to {self.recipient_email} - {self.status}"