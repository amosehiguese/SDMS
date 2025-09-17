import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import MinValueValidator
from core.models import BaseModel

class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='children')
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Product(BaseModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    
    # Pricing
    price = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(Decimal('0'))])
    sale_price = models.DecimalField(max_digits=12, decimal_places=0, blank=True, null=True, validators=[MinValueValidator(Decimal('0'))])
    
    # Flash sale settings
    flash_sale_enabled = models.BooleanField(default=False)
    flash_sale_end_time = models.DateTimeField(blank=True, null=True)
    
    # Inventory
    stock_quantity = models.PositiveIntegerField(default=0)
    track_stock = models.BooleanField(default=True)
    allow_backorder = models.BooleanField(default=False)
    
    # Product attributes
    sku = models.CharField(max_length=100, unique=True, blank=True)
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Weight in kg")
    dimensions = models.CharField(max_length=100, blank=True, help_text="L x W x H in cm")
    
    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # SEO
    meta_title = models.CharField(max_length=60, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'is_featured']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['flash_sale_enabled', 'flash_sale_end_time']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.sku:
            self.sku = f"SKU-{str(self.id)[:8]}" if self.id else f"SKU{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)
    
    def get_display_price(self):
        """Get the price to display (considering flash sales)"""
        if self.has_active_flash_sale() or self.sale_price:
            return self.sale_price
        return self.price
    
    def get_savings(self):
        """Get savings amount if on flash sale"""
        if self.has_active_flash_sale() and self.sale_price:
            return self.price - self.sale_price
        return Decimal('0.00')
    
    def get_savings_percentage(self):
        """Get savings percentage if on flash sale"""
        if self.has_active_flash_sale() and self.sale_price:
            return round(((self.price - self.sale_price) / self.price) * 100, 1)
        return 0
    
    def has_active_flash_sale(self):
        """Check if product has an active flash sale"""
        if not self.flash_sale_enabled or not self.flash_sale_end_time:
            return False
        return timezone.now() < self.flash_sale_end_time
    
    def is_in_stock(self):
        """Check if product is in stock"""
        if not self.track_stock:
            return True
        return self.stock_quantity > 0 or self.allow_backorder
    
    def can_purchase(self, quantity=1):
        """Check if product can be purchased with given quantity"""
        if not self.is_active:
            return False
        if not self.track_stock:
            return True
        if self.allow_backorder:
            return True
        return self.stock_quantity >= quantity
    
    def reduce_stock(self, quantity):
        """Reduce stock quantity"""
        if self.track_stock and self.stock_quantity >= quantity:
            self.stock_quantity -= quantity
            self.save(update_fields=['stock_quantity'])
            return True
        return False

class ProductImage(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['sort_order', 'created_at']
    
    def __str__(self):
        return f"{self.product.title} - Image {self.sort_order}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

class ProductReview(BaseModel):
    RATING_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=200)
    comment = models.TextField()
    is_verified_purchase = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.product.title} - {self.rating} stars by {self.user.email}"