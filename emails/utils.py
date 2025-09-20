from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.conf import settings
from .tasks import send_email_task, send_user_email_task, send_admin_email_task

import uuid
from datetime import datetime
from django.utils.timezone import is_naive, make_aware, get_current_timezone



def serialize_for_task(value):
    """Ensure values are JSON-serializable for Celery tasks"""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        if is_naive(value):
            value = make_aware(value, timezone=get_current_timezone())
        return value.isoformat()
    return value

def send_test_email(email_type, recipient_email, context=None):
    """
    Send test email immediately (not async) for testing purposes
    """
    from .services import EmailService
    return EmailService.send_email(email_type, recipient_email, context)

def send_notification_email(email_type, user=None, context=None):
    """
    Convenient function to send notification emails
    """
    if user:
        return send_user_email_task.delay(email_type, user.id, context)
    else:
        return send_admin_email_task.delay(email_type, context)

def send_bulk_notification(email_type, users, context=None):
    """
    Send bulk notification to multiple users
    """
    from .tasks import send_bulk_email_task
    
    recipient_emails = [user.email for user in users]
    return send_bulk_email_task.delay(email_type, recipient_emails, context)

def get_email_stats():
    """
    Get email statistics for dashboard
    """
    from .models import EmailLog
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    stats = {
        'today': {
            'total': EmailLog.objects.filter(created_at__date=today).count(),
            'sent': EmailLog.objects.filter(created_at__date=today, status='sent').count(),
            'failed': EmailLog.objects.filter(created_at__date=today, status='failed').count(),
        },
        'week': {
            'total': EmailLog.objects.filter(created_at__gte=week_ago).count(),
            'sent': EmailLog.objects.filter(created_at__gte=week_ago, status='sent').count(),
            'failed': EmailLog.objects.filter(created_at__gte=week_ago, status='failed').count(),
        },
        'month': {
            'total': EmailLog.objects.filter(created_at__gte=month_ago).count(),
            'sent': EmailLog.objects.filter(created_at__gte=month_ago, status='sent').count(),
            'failed': EmailLog.objects.filter(created_at__gte=month_ago, status='failed').count(),
        },
        'by_type': EmailLog.objects.filter(created_at__gte=week_ago).values('email_type').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
    }
    
    return stats

def cleanup_old_email_logs(days=90):
    """
    Clean up old email logs older than specified days
    """
    from .models import EmailLog
    from django.utils import timezone
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    deleted_count = EmailLog.objects.filter(created_at__lt=cutoff_date).count()
    EmailLog.objects.filter(created_at__lt=cutoff_date).delete()
    
    return deleted_count

def validate_email_template(template_path, context=None):
    """
    Validate if email template can be rendered with given context
    """
    if context is None:
        context = {}
        
    try:
        render_to_string(template_path, context)
        return True, None
    except Exception as e:
        return False, str(e)

def preview_email(email_type, context=None):
    """
    Preview email content without sending
    """
    from .services import EmailService
    
    config = EmailService.get_email_config(email_type)
    if not config:
        return None, "Email type not found"
    
    full_context = EmailService.prepare_context(context or {}, email_type)
    
    try:
        html_content = render_to_string(config['template'], full_context)
        subject = config['subject'].format(**full_context)
        return {
            'subject': subject,
            'html_content': html_content,
            'context': full_context
        }, None
    except Exception as e:
        return None, str(e)

        