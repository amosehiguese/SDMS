from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import SiteConfiguration

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group

from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass

@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(ModelAdmin):
    fieldsets = (
        ('Site Branding', {
            'fields': ('site_name', 'site_logo', 'site_favicon')
        }),
        ('Payment Settings', {
            'fields': ('paystack_public_key', 'paystack_secret_key')
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'phone_number', 'whatsapp_number')
        }),
        ('Address Information', {
            'fields': ('address',)
        }),
        ('Business Information', {
            'fields': ('business_hours',)
        }),
        ('Social Media', {
            'fields': ('facebook_url', 'twitter_url', 'instagram_url', 'linkedin_url', 'youtube_url'),
            'classes': ('collapse',)
        }),
        ('Footer Content', {
            'fields': ('footer_about_text', 'copyright_text')
        }),
        ('Site Features', {
            'fields': ('flash_sales_enabled', 'blog_enabled', 'user_reviews_enabled')
        }),
        ('Hero Banner Settings', {
            'fields': ('hero_banner_enabled', 'hero_button_enabled', 'hero_banner_image', 'hero_banner_title', 'hero_banner_subtitle', 'hero_banner_button_text', 'hero_banner_button_action'),
            'classes': ('collapse',)
        }),
        ('Countdown Settings', {
            'fields': ('countdown_enabled', 'countdown_duration_hours', 'countdown_reset_daily'),
            'classes': ('collapse',)
        }),
        ('Shipping Settings', {
            'fields': ('default_shipping_cost', 'free_shipping_threshold')
        }),
        ('Tax Settings', {
            'fields': ('tax_rate',)
        }),
        ('Inventory Settings', {
            'fields': ('low_stock_threshold',),
            'description': 'Configure inventory management settings'
        }),
        ('SEO Settings', {
            'fields': ('meta_title', 'meta_description', 'meta_keywords'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one configuration
        return not SiteConfiguration.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion of site configuration
        return False
