from django.contrib import admin
from unfold.admin import ModelAdmin
from django.utils.html import format_html
from django.utils import timezone
from .models import EmailTemplate, EmailLog

@admin.register(EmailTemplate)
class EmailTemplateAdmin(ModelAdmin):
    list_display = ('email_type', 'recipient_type', 'subject', 'is_active', 'updated_at')
    list_filter = ('recipient_type', 'is_active', 'email_type')
    search_fields = ('email_type', 'subject', 'template_path')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('email_type', 'recipient_type', 'is_active')
        }),
        ('Email Content', {
            'fields': ('subject', 'template_path'),
            'description': 'Use {variable} syntax for dynamic content like {site_name}, {user.email}, {order.order_number}'
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        
        # Add help text for common variables
        if 'subject' in form.base_fields:
            help_text = """
            <br><strong>Available variables:</strong><br>
            <code>{site_name}</code> - Site name<br>
            <code>{user.email}</code> - User email<br>
            <code>{user.first_name}</code> - User first name<br>
            <code>{order.order_number}</code> - Order number<br>
            <code>{order.total}</code> - Order total<br>
            <code>{product.title}</code> - Product title<br>
            <code>{submission.title}</code> - Submission title
            """
            form.base_fields['subject'].help_text = format_html(help_text)
            
        return form

@admin.register(EmailLog)
class EmailLogAdmin(ModelAdmin):
    list_display = ('email_type', 'recipient_email', 'status', 'created_at', 'sent_at')
    list_filter = ('status', 'email_type', 'created_at')
    search_fields = ('recipient_email', 'subject', 'email_type')
    readonly_fields = ('id', 'created_at', 'context_data')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Email Information', {
            'fields': ('email_type', 'recipient_email', 'subject', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'sent_at'),
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',),
        }),
        ('Context Data', {
            'fields': ('context_data',),
            'classes': ('collapse',),
            'description': 'JSON data used to render the email template'
        }),
        ('Metadata', {
            'fields': ('id',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Only allow deletion of old logs
        if obj and obj.created_at < timezone.now() - timezone.timedelta(days=90):
            return True
        return False
    
    actions = ['retry_failed_emails']
    
    def retry_failed_emails(self, request, queryset):
        """Action to retry failed emails"""
        from .tasks import send_email_task
        
        failed_emails = queryset.filter(status='failed')
        count = 0
        
        for email_log in failed_emails:
            try:
                # Retry the email
                send_email_task.delay(
                    email_log.email_type,
                    email_log.recipient_email,
                    email_log.context_data
                )
                count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Failed to retry email {email_log.id}: {str(e)}",
                    level='ERROR'
                )
        
        if count > 0:
            self.message_user(
                request,
                f"Successfully queued {count} emails for retry.",
                level='SUCCESS'
            )
    
    retry_failed_emails.short_description = "Retry selected failed emails"
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related().order_by('-created_at')