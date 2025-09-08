from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from .models import Order, OrderItem, ShippingAddress, Cart, CartItem, Receipt, OrderStatusLog

class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price', 'get_total_price')
    
    def get_total_price(self, obj):
        return f'₦{obj.get_total_price()}'
    get_total_price.short_description = 'Total'

class OrderStatusLogInline(TabularInline):
    model = OrderStatusLog
    extra = 0
    readonly_fields = ('previous_status', 'new_status', 'changed_by', 'created_at')

@admin.register(ShippingAddress)
class ShippingAddressAdmin(ModelAdmin):
    list_display = ('get_full_name', 'user_email', 'city', 'state', 'is_default')
    list_filter = ('is_default', 'state', 'city', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'city', 'state')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('user', 'first_name', 'last_name', 'email', 'phone')
        }),
        ('Address Information', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country')
        }),
        ('Settings', {
            'fields': ('is_default',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    get_full_name.short_description = 'Full Name'
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'

@admin.register(Cart)
class CartAdmin(ModelAdmin):
    list_display = ('user', 'item_count', 'total_amount', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    
    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'
    
    def total_amount(self, obj):
        return f'₦{obj.get_total()}'
    total_amount.short_description = 'Total'

@admin.register(CartItem)
class CartItemAdmin(ModelAdmin):
    list_display = ('cart', 'product', 'quantity', 'get_total_price', 'created_at')
    list_filter = ('created_at', 'product__category')
    search_fields = ('cart__user__email', 'product__title')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_total_price(self, obj):
        return f'₦{obj.get_total_price()}'
    get_total_price.short_description = 'Total Price'

@admin.register(Receipt)
class ReceiptAdmin(ModelAdmin):
    list_display = ('order', 'receipt_number', 'total_amount', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('receipt_number', 'order__order_number')
    readonly_fields = ('receipt_number', 'created_at', 'updated_at')
    
    def total_amount(self, obj):
        return f'₦{obj.order.total}'
    total_amount.short_description = 'Total Amount'

@admin.register(OrderStatusLog)
class OrderStatusLogAdmin(ModelAdmin):
    list_display = ('order', 'previous_status', 'new_status', 'changed_by', 'created_at')
    list_filter = ('previous_status', 'new_status', 'created_at')
    search_fields = ('order__order_number', 'changed_by__email')
    readonly_fields = ('order', 'previous_status', 'new_status', 'changed_by', 'created_at')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ('order_number', 'user_email', 'status_display', 'fulfillment_type', 'total', 'created_at')
    list_filter = ('status', 'fulfillment_type', 'created_at', 'paid_at')
    search_fields = ('order_number', 'user__email', 'payment_reference')
    readonly_fields = ('order_number', 'subtotal', 'tax_amount', 'total', 'created_at', 'updated_at')
    inlines = [OrderItemInline, OrderStatusLogInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'user', 'status', 'fulfillment_type', 'created_at', 'updated_at')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'shipping_cost', 'tax_amount', 'total')
        }),
        ('Payment Information', {
            'fields': ('payment_reference', 'payment_method', 'paid_at')
        }),
        ('Shipping Information', {
            'fields': ('shipping_address', 'tracking_number', 'shipped_at', 'delivered_at')
        }),
        ('Notes', {
            'fields': ('customer_notes', 'admin_notes'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Customer'
    
    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'paid': 'blue',
            'shipped': 'purple',
            'delivered': 'green',
            'cancelled': 'red',
        }
        color = colors.get(obj.status, 'gray')
        obj_display = obj.get_status_display()
        return format_html(
            f'<span style="color: {color}; font-weight: bold;">{obj_display}</span>',
        )
    status_display.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        # Log status changes
        if change:
            old_obj = Order.objects.get(pk=obj.pk)
            if old_obj.status != obj.status:
                OrderStatusLog.objects.create(
                    order=obj,
                    previous_status=old_obj.status,
                    new_status=obj.status,
                    changed_by=request.user
                )
        super().save_model(request, obj, form, change)
