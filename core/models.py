import uuid
from django.db import models
from django.core.validators import EmailValidator, RegexValidator

class SiteConfiguration(models.Model):
    """Site-wide configuration settings"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Site branding
    site_name = models.CharField(max_length=200, default="SuccessDirectMarketStore")
    site_logo = models.ImageField(upload_to='branding/', blank=True, null=True)
    site_favicon = models.ImageField(upload_to='branding/', blank=True, null=True)
    
    # Payment settings
    paystack_public_key = models.CharField(max_length=200, blank=True)
    paystack_secret_key = models.CharField(max_length=200, blank=True)
    
    # Contact information
    contact_email = models.EmailField(validators=[EmailValidator()])
    phone_number = models.CharField(
        max_length=20, 
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")]
    )
    whatsapp_number = models.CharField(
        max_length=20, 
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message="WhatsApp number must be entered in the format: '+999999999'. Up to 15 digits allowed.")],
        blank=True
    )
    
    # Address information
    address = models.CharField(max_length=255)
    
    # Social media links
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    
    # Footer content
    footer_about_text = models.TextField(max_length=500, blank=True, help_text="Short description for footer")
    copyright_text = models.CharField(max_length=200, default="© 2024 SuccessDirectMarketStore. All rights reserved.")
    
    # Business hours
    business_hours = models.TextField(blank=True, help_text="Enter business hours, e.g., 'Mon-Fri: 9AM-6PM'")
    
    # Site features
    flash_sales_enabled = models.BooleanField(default=True)
    blog_enabled = models.BooleanField(default=True)
    user_reviews_enabled = models.BooleanField(default=True)
    
    # Hero Banner Settings
    hero_banner_enabled = models.BooleanField(default=True, help_text="Enable/disable hero banner on homepage")
    hero_banner_image = models.ImageField(upload_to='hero_banner/', blank=True, null=True, help_text="Hero banner background image")
    hero_banner_title = models.CharField(max_length=200, default="Flash Sale", help_text="Hero banner title")
    hero_banner_subtitle = models.CharField(max_length=300, default="Up to 70% off on selected items!", help_text="Hero banner subtitle")
    hero_banner_button_text = models.CharField(max_length=100, default="Shop Flash Sale", help_text="Hero banner button text")
    hero_banner_button_action = models.CharField(max_length=200, default="flash sale", help_text="Search term when button is clicked")
    
    # Countdown Settings
    countdown_enabled = models.BooleanField(default=True, help_text="Enable/disable countdown timer")
    countdown_duration_hours = models.PositiveIntegerField(default=24, help_text="Countdown duration in hours")
    countdown_reset_daily = models.BooleanField(default=True, help_text="Reset countdown daily at midnight")
    
    # Email templates
    welcome_email_subject = models.CharField(max_length=200, default="Welcome to SuccessDirectMarketStore!")
    order_confirmation_subject = models.CharField(max_length=200, default="Order Confirmation - #{order_number}")
    receipt_email_subject = models.CharField(max_length=200, default="Payment Receipt - #{order_number}")
    
    # Shipping settings
    default_shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    free_shipping_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Tax settings
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.0750, help_text="Tax rate as decimal (e.g., 0.0750 for 7.5%)")
    
    # SEO settings
    meta_title = models.CharField(max_length=60, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)
    meta_keywords = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"
    
    def __str__(self):
        return f"Site Configuration - {self.site_name}"
    
    def save(self, *args, **kwargs):
        # Ensure only one configuration instance exists
        if not self.pk and SiteConfiguration.objects.exists():
            raise ValueError("Only one site configuration is allowed")
        return super().save(*args, **kwargs)
    
    @classmethod
    def get_config(cls):
        """Get or create site configuration"""
        config, created = cls.objects.get_or_create(pk=1)
        return config

class BaseModel(models.Model):
    """Base model with common fields"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
