import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import EmailValidator, RegexValidator
from core.models import BaseModel
from store.models import Product

class ShippingAddress(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shipping_addresses')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(validators=[EmailValidator()])
    phone = models.CharField(
        max_length=20,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")]
    )
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="Nigeria")
    is_default = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Shipping Addresses"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.city}, {self.state}"
    
    def save(self, *args, **kwargs):
        # Ensure only one default address per user
        if self.is_default:
            ShippingAddress.objects.filter(user=self.user, is_default=True).update(is_default=False)
    def save(self, *args, **kwargs):
        # Set price from product if not set
        if not self.price:
            self.price = self.product.get_display_price()
        super().save(*args, **kwargs)

class Cart(BaseModel):
    """Shopping cart for logged-in users"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    
    def __str__(self):
        return f"Cart for {self.user.email}"
    
    def get_total_items(self):
        """Get total number of items in cart"""
        return sum(item.quantity for item in self.items.all())
    
    def get_subtotal(self):
        """Get cart subtotal"""
        return sum(item.get_total_price() for item in self.items.all())
    
    def clear(self):
        """Clear all items from cart"""
        self.items.all().delete()

class CartItem(BaseModel):
    """Items in shopping cart"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    
    class Meta:
        unique_together = ('cart', 'product')
    
    def __str__(self):
        return f"{self.product.title} x {self.quantity}"
    
    def get_total_price(self):
        """Get total price for this cart item"""
        return self.product.get_display_price() * self.quantity
    
    def can_add_quantity(self, additional_quantity=1):
        """Check if we can add more quantity"""
        total_quantity = self.quantity + additional_quantity
        return self.product.can_purchase(total_quantity)

class Receipt(BaseModel):
    """Receipt for completed orders"""
    order = models.OneToOneField("Order", on_delete=models.CASCADE, related_name='receipt')
    receipt_number = models.CharField(max_length=20, unique=True, blank=True)
    receipt_data = models.JSONField()  # Store receipt details as JSON
    pdf_file = models.FileField(upload_to='receipts/', blank=True, null=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Receipt {self.receipt_number} for Order {self.order.order_number}"
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            import random
            self.receipt_number = f"RCP{random.randint(100000, 999999)}"
        super().save(*args, **kwargs)

class OrderStatusLog(BaseModel):
    """Log order status changes"""
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name='status_logs')
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Order {self.order.order_number}: {self.previous_status} → {self.new_status}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_address(self):
        address = f"{self.address_line_1}"
        if self.address_line_2:
            address += f", {self.address_line_2}"
        address += f", {self.city}, {self.state} {self.postal_code}, {self.country}"
        return address

class Order(BaseModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    FULFILLMENT_CHOICES = [
        ('hold_asset', 'Hold as Asset'),
        ('deliver', 'Deliver to Me'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=20, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    fulfillment_type = models.CharField(max_length=20, choices=FULFILLMENT_CHOICES, default='deliver')
    
    # Pricing
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Shipping information (only for 'deliver' fulfillment type)
    shipping_address = models.ForeignKey(ShippingAddress, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Tracking information
    tracking_number = models.CharField(max_length=100, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Payment information
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=50, default='paystack')
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Special notes
    customer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['fulfillment_type']),
        ]
    
    def __str__(self):
        return f"Order {self.order_number} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generate order number
            import random
            self.order_number = f"ORD{random.randint(100000, 999999)}"
        super().save(*args, **kwargs)
    
    def calculate_totals(self):
        """Calculate order totals based on items"""
        self.subtotal = sum(item.get_total_price() for item in self.items.all())
        
        # Add shipping cost only for delivery orders
        if self.fulfillment_type == 'deliver':
            from core.models import SiteConfiguration
            config = SiteConfiguration.get_config()
            if self.subtotal < config.free_shipping_threshold:
                self.shipping_cost = config.default_shipping_cost
            else:
                self.shipping_cost = Decimal('0.00')
        else:
            self.shipping_cost = Decimal('0.00')
        
        # Calculate tax from site configuration
        from core.models import SiteConfiguration
        config = SiteConfiguration.get_config()
        tax_rate = getattr(config, 'tax_rate', Decimal('0.00'))
        self.tax_amount = self.subtotal * tax_rate
        
        self.total = self.subtotal + self.shipping_cost + self.tax_amount
        self.save(update_fields=['subtotal', 'shipping_cost', 'tax_amount', 'total'])
    
    def can_be_cancelled(self):
        """Check if order can be cancelled"""
        return self.status in ['pending', 'paid']
    
    def can_be_shipped(self):
        """Check if order can be shipped"""
        return self.status == 'paid' and self.fulfillment_type == 'deliver'
    
    def can_be_delivered(self):
        """Check if order can be marked as delivered"""
        return self.status == 'shipped'
    
    def get_held_assets(self):
        """Get items that are held as assets"""
        if self.fulfillment_type == 'hold_asset':
            return self.items.all()
        return self.items.none()
    
    def liquidate_assets(self, shipping_address):
        """Convert held assets to delivery order"""
        if self.fulfillment_type == 'hold_asset' and self.status == 'paid':
            self.fulfillment_type = 'deliver'
            self.shipping_address = shipping_address
            self.status = 'paid'  # Keep paid status
            self.calculate_totals()  # Recalculate with shipping
            self.save()
            return True
        return False

class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    
    class Meta:
        unique_together = ('order', 'product')
    
    def __str__(self):
        return f"{self.product.title} x {self.quantity}"
    
    def get_total_price(self):
        """Get total price for this item"""
        return self.price * self.quantity
    
    def save(self, *args, **kwargs):
        # Set price from product if not set
        if not self.price:
            self.price = self.product.get_display_price()
        super().save(*args, **kwargs)