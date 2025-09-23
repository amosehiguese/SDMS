from django.contrib import admin
from unfold.admin import ModelAdmin
from django.utils import timezone
from .models import EmailLog

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