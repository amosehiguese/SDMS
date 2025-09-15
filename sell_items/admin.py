from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import SellItemSubmission, SellItemImage

class SellItemImageInline(TabularInline):
    model = SellItemImage
    extra = 0
    fields = ['image', 'alt_text', 'is_primary', 'sort_order']

@admin.register(SellItemSubmission)
class SellItemSubmissionAdmin(ModelAdmin):
    list_display = ['title', 'user', 'price', 'stock_quantity', 'source', 'status', 'created_at']
    list_filter = ['status', 'source', 'category', 'created_at']
    search_fields = ['title', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [SellItemImageInline]
    
    fieldsets = (
        ('Item Information', {
            'fields': ('title', 'description', 'category', 'price', 'stock_quantity')
        }),
        ('Product Attributes', {
            'fields': ('weight', 'dimensions'),
            'classes': ('collapse',)
        }),
        ('Bank Account Details', {
            'fields': ('bank_name', 'account_number', 'account_holder_name'),
            'classes': ('collapse',)
        }),
        ('Submission Details', {
            'fields': ('user', 'source', 'held_asset_order')
        }),
        ('Review Status', {
            'fields': ('status', 'admin_notes', 'reviewed_by', 'reviewed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data:
            obj.reviewed_by = request.user
            from django.utils import timezone
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)

@admin.register(SellItemImage)
class SellItemImageAdmin(ModelAdmin):
    list_display = ['submission', 'is_primary', 'sort_order']
    list_filter = ['is_primary', 'submission__status']
    search_fields = ['submission__title', 'alt_text']