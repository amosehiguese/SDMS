from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Payment, PaymentWebhook

@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = [
        'payment_reference', 'user', 'order', 'amount', 'currency', 
        'status', 'payment_method', 'created_at'
    ]
    list_filter = [
        'status', 'payment_method', 'currency', 'created_at', 'completed_at'
    ]
    search_fields = [
        'payment_reference', 'external_transaction_id', 'user__email', 
        'order__order_number', 'customer_email'
    ]
    readonly_fields = [
        'payment_reference', 'external_transaction_id', 'created_at', 'updated_at',
        'initiated_at', 'processed_at', 'completed_at', 'gateway_data'
    ]
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_reference', 'external_transaction_id', 'status', 'payment_method')
        }),
        ('Order Details', {
            'fields': ('order', 'user', 'amount', 'currency')
        }),
        ('Customer Information', {
            'fields': ('customer_email', 'customer_phone', 'customer_name')
        }),
        ('Timestamps', {
            'fields': ('initiated_at', 'processed_at', 'completed_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_code'),
            'classes': ('collapse',)
        }),
        ('Gateway Data', {
            'fields': ('gateway_data',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Payments should only be created through the payment flow
        return False
    

@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(ModelAdmin):
    list_display = [
        'webhook_id', 'gateway_name', 'event_type', 'payment_reference', 'processed', 'created_at'
    ]
    list_filter = ['gateway_name', 'event_type', 'processed', 'created_at']
    search_fields = ['webhook_id', 'payment_reference', 'event_type']
    readonly_fields = [
        'webhook_id', 'gateway_name', 'event_type', 'payment_reference', 'webhook_data',
        'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Webhook Information', {
            'fields': ('webhook_id', 'gateway_name', 'event_type', 'payment_reference')
        }),
        ('Processing Status', {
            'fields': ('processed', 'processed_at')
        }),
        ('Webhook Data', {
            'fields': ('webhook_data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Webhooks should only be created through payment gateways
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion of webhook records
        return False
