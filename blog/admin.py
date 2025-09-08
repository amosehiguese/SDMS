from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import BlogCategory, BlogTag, BlogPost, BlogComment, BlogPostView

@admin.register(BlogCategory)
class BlogCategoryAdmin(ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'sort_order', 'post_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['sort_order', 'name']
    
    def post_count(self, obj):
        return obj.posts.filter(status='published').count()
    post_count.short_description = 'Published Posts'

@admin.register(BlogTag)
class BlogTagAdmin(ModelAdmin):
    list_display = ['name', 'slug', 'color', 'post_count', 'created_at']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['name']
    
    def post_count(self, obj):
        return obj.posts.filter(status='published').count()
    post_count.short_description = 'Posts'

class BlogCommentInline(admin.TabularInline):
    model = BlogComment
    extra = 0
    readonly_fields = ['author', 'content', 'created_at']
    fields = ['author', 'content', 'is_approved', 'is_featured', 'created_at']

@admin.register(BlogPost)
class BlogPostAdmin(ModelAdmin):
    list_display = [
        'title', 'author', 'category', 'status', 'featured', 
        'view_count', 'like_count', 'published_at', 'created_at'
    ]
    list_filter = [
        'status', 'featured', 'category', 'tags', 'author', 
        'published_at', 'created_at'
    ]
    search_fields = ['title', 'excerpt', 'content', 'author__username']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['tags']
    inlines = [BlogCommentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'excerpt', 'author')
        }),
        ('Content', {
            'fields': ('content', 'content_html'),
            'classes': ('wide',)
        }),
        ('Categorization', {
            'fields': ('category', 'tags')
        }),
        ('Publishing', {
            'fields': ('status', 'featured', 'published_at')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
        ('Engagement', {
            'fields': ('view_count', 'like_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['content_html', 'view_count', 'like_count', 'created_at', 'updated_at']
    
    def save_model(self, request, obj, form, change):
        if not change:  # New post
            obj.author = request.user
        super().save_model(request, obj, form, change)

@admin.register(BlogComment)
class BlogCommentAdmin(ModelAdmin):
    list_display = [
        'post', 'author', 'is_approved', 'is_featured', 
        'is_reply', 'created_at'
    ]
    list_filter = ['is_approved', 'is_featured', 'created_at']
    search_fields = ['content', 'author__username', 'post__title']
    readonly_fields = ['post', 'author', 'content', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Comment Information', {
            'fields': ('post', 'author', 'content')
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_featured')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def is_reply(self, obj):
        return obj.is_reply
    is_reply.boolean = True
    is_reply.short_description = 'Is Reply'

@admin.register(BlogPostView)
class BlogPostViewAdmin(ModelAdmin):
    list_display = ['post', 'user', 'ip_address', 'created_at']
    list_filter = ['created_at', 'post__category']
    search_fields = ['post__title', 'ip_address', 'user__username']
    readonly_fields = ['post', 'user', 'ip_address', 'user_agent', 'referer', 'created_at']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
