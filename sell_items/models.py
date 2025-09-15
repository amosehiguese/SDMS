from django.db import models
from django.contrib.auth.models import User
from core.models import BaseModel
from decimal import Decimal
from django.core.validators import MinValueValidator

class SellItemSubmission(BaseModel):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    SOURCE_CHOICES = [
        ('own_item', 'Own Item'),
        ('held_asset', 'Held Asset'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sell_submissions')
    
    # Product details (same as Product model)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey('store.Category', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(Decimal('0'))])
    
    # Product attributes
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Weight in kg")
    dimensions = models.CharField(max_length=100, blank=True, help_text="L x W x H in cm")
    
    # Stock quantity 
    stock_quantity = models.PositiveIntegerField(default=1, help_text="Number of items available for sale")

    # Bank account details
    bank_name = models.CharField(max_length=100, blank=True, help_text="Name of your bank")
    account_number = models.CharField(max_length=20, blank=True, help_text="Your bank account number")
    account_holder_name = models.CharField(max_length=100, blank=True, help_text="Name on the bank account")

    # Submission details
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='own_item')
    held_asset_order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, help_text="Admin's reason for acceptance/rejection")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_submissions')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    @property
    def has_complete_bank_details(self):
        """Check if all bank account details are provided"""
        return all([self.bank_name, self.account_number, self.account_holder_name])
    
    @property
    def max_allowed_quantity(self):
        """Get maximum allowed quantity based on source"""
        if self.source == 'held_asset' and self.held_asset_order:
            order_item = self.held_asset_order.items.first()
            if order_item:
                return order_item.get_available_quantity(submission_to_exclude=self)
            return 0
        return None  # No limit for own items
    
    def clean(self):
        """Validate stock quantity against held asset limits"""
        from django.core.exceptions import ValidationError
        
        if self.source == 'held_asset' and self.max_allowed_quantity:
            if self.stock_quantity > self.max_allowed_quantity:
                raise ValidationError({
                    'stock_quantity': f'Stock quantity cannot exceed {self.max_allowed_quantity} (original purchase quantity)'
                })
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

class SellItemImage(BaseModel):
    submission = models.ForeignKey(SellItemSubmission, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='sell_items/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['sort_order', 'created_at']
    
    def __str__(self):
        return f"{self.submission.title} - Image {self.sort_order}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary image per submission
        if self.is_primary:
            SellItemImage.objects.filter(submission=self.submission, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)