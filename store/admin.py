from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Category, Product, ProductImage, ProductReview

class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'is_primary', 'sort_order')
    ordering = ('sort_order',)

@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'parent', 'is_active', 'product_count', 'created_at')
    list_filter = ('is_active', 'parent', 'created_at')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    
    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'

@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ('title', 'category', 'price_display', 'stock_status', 'flash_sale_status', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_featured', 'flash_sale_enabled', 'category', 'created_at')
    search_fields = ('title', 'description', 'sku')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ProductImageInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description', 'category', 'sku')
        }),
        ('Pricing', {
            'fields': ('price', 'sale_price')
        }),
        ('Flash Sale', {
            'fields': ('flash_sale_enabled', 'flash_sale_end_time'),
            'classes': ('collapse',)
        }),
        ('Inventory', {
            'fields': ('stock_quantity', 'track_stock', 'allow_backorder')
        }),
        ('Product Details', {
            'fields': ('weight', 'dimensions'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
    )
    
    def price_display(self, obj):
        if obj.has_active_flash_sale() and obj.sale_price:
            return format_html(
                f'<span style="text-decoration: line-through;">₦{obj.price}</span> <span style="color: red;">₦{obj.sale_price}</span>',
            )
        return f'₦{obj.price}'
    price_display.short_description = 'Price'
    
    def stock_status(self, obj):
        if not obj.track_stock:
            return format_html(f'<span style="color: blue;">Not Tracked</span>')
        elif obj.stock_quantity > 10:
            return format_html(f'<span style="color: green;">In Stock ({obj.stock_quantity})</span>')
        elif obj.stock_quantity > 0:
            return format_html(f'<span style="color: orange;">Low Stock ({obj.stock_quantity})</span>')
        elif obj.allow_backorder:
            return format_html(f'<span style="color: red;">Backorder</span>')
        else:
            return format_html(f'<span style="color: red;">Out of Stock</span>')
    stock_status.short_description = 'Stock'
    
    def flash_sale_status(self, obj):
        if obj.has_active_flash_sale():
            return format_html(f'<span style="color: red;">Active</span>')
        elif obj.flash_sale_enabled:
            return format_html(f'<span style="color: orange;">Expired</span>')
        return format_html(f'<span style="color: gray;">Disabled</span>')
    flash_sale_status.short_description = 'Flash Sale'

@admin.register(ProductImage)
class ProductImageAdmin(ModelAdmin):
    list_display = ('product', 'image_preview', 'is_primary', 'sort_order')
    list_filter = ('is_primary', 'created_at')
    search_fields = ('product__title', 'alt_text')
    
    def image_preview(self, obj):
        if obj.image:
            return format_html(f'<img src="{obj.image.url}" style="width: 50px; height: 50px; object-fit: cover;">')
        return "No Image"
    image_preview.short_description = 'Preview'

@admin.register(ProductReview)
class ProductReviewAdmin(ModelAdmin):
    list_display = ('product', 'user', 'rating', 'title', 'is_verified_purchase', 'is_approved', 'created_at')
    list_filter = ('rating', 'is_verified_purchase', 'is_approved', 'created_at')
    search_fields = ('product__title', 'user__email', 'title', 'comment')
    readonly_fields = ('user', 'product', 'created_at')
    
    def has_add_permission(self, request):
        return False  
