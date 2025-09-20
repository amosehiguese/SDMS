import json
import logging
from datetime import datetime
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from .models import EmailTemplate, EmailLog

logger = logging.getLogger(__name__)

class EmailService:
    """Service for handling all email operations"""

    # Default email configurations
    DEFAULT_TEMPLATES = {
        'welcome': {
            'subject': 'Welcome to {site_name}!',
            'template': 'emails/user/welcome.html',
            'recipient_type': 'user'
        },
        'order_confirmation': {
            'subject': 'Order #{order_number} Confirmed',
            'template': 'emails/user/order_confirmation.html',
            'recipient_type': 'user'
        },
        'order_shipped': {
            'subject': 'Order #{order_number} Shipped',
            'template': 'emails/user/order_shipped.html',
            'recipient_type': 'user'
        },
        'order_delivered': {
            'subject': 'Order #{order_number} Delivered',
            'template': 'emails/user/order_delivered.html',
            'recipient_type': 'user'
        },
        'receipt': {
            'subject': 'Receipt for Order #{order_number}',
            'template': 'emails/user/receipt.html',
            'recipient_type': 'user'
        },
        'asset_liquidation': {
            'subject': 'Asset Liquidation Request Submitted',
            'template': 'emails/user/asset_liquidation.html',
            'recipient_type': 'user'
        },
        'sell_item_submitted': {
            'subject': 'Your Item Submission is Under Review',
            'template': 'emails/user/sell_item_submitted.html',
            'recipient_type': 'user'
        },
        'sell_item_approved': {
            'subject': 'Your Item Has Been Approved for Sale!',
            'template': 'emails/user/sell_item_approved.html',
            'recipient_type': 'user'
        },
        'sell_item_rejected': {
            'subject': 'Item Submission Update',
            'template': 'emails/user/sell_item_rejected.html',
            'recipient_type': 'user'
        },
        
        # Admin emails
        'new_order_admin': {
            'subject': 'New Order #{order_number} Received',
            'template': 'emails/admin/new_order.html',
            'recipient_type': 'admin'
        },
        'new_user_admin': {
            'subject': 'New User Registration: {user_email}',
            'template': 'emails/admin/new_user.html',
            'recipient_type': 'admin'
        },
        'sell_item_review_admin': {
            'subject': 'New Item Submission Requires Review',
            'template': 'emails/admin/sell_item_review.html',
            'recipient_type': 'admin'
        },
        'low_stock_admin': {
            'subject': 'Low Stock Alert: {product_title}',
            'template': 'emails/admin/low_stock.html',
            'recipient_type': 'admin'
        },
        'payment_failed_admin': {
            'subject': 'Payment Failed for Order #{order_number}',
            'template': 'emails/admin/payment_failed.html',
            'recipient_type': 'admin'
        },
        'admin_message': {
            'subject': '{{ subject }}',
            'template': 'emails/user/admin_message.html',
            'description': 'Admin message to users',
            'recipient_type': 'user'
        },
    }
    
    
    ADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', 'admin@successdirectmarketstores.com')
    FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@successdirectmarketstores.com')
    
    @classmethod
    def send_email(cls, email_type, recipient_email, context=None):
        """
        Send email with improved error handling and context serialization
        """
        try:
            try:
                template = EmailTemplate.objects.get(email_type=email_type, is_active=True)
            except EmailTemplate.DoesNotExist:
                logger.error(f"Email template not found: {email_type}")
                return False
            
            if context is None:
                context = {}
            
            cleaned_context = cls._clean_context_for_serialization(context)

            subject = cls._render_template_string(template.subject, cleaned_context)

            try:
                html_content = render_to_string(template.template_path, cleaned_context)
                text_content = strip_tags(html_content)
            except Exception as e:
                logger.error(f"Template rendering failed for {email_type}: {str(e)}")
                return False
            
            email_log = EmailLog.objects.create(
                email_type=email_type,
                recipient_email=recipient_email,
                subject=subject,
                status='pending',
                context_data=cleaned_context  
            )
            
            try:
                send_mail(
                    subject=subject,
                    message=text_content,
                    from_email=cls.FROM_EMAIL,
                    recipient_list=[recipient_email],
                    html_message=html_content,
                    fail_silently=False
                )
                
                email_log.status = 'sent'
                email_log.sent_at = datetime.now()
                email_log.save()
                
                logger.info(f"Email sent successfully: {email_type} to {recipient_email}")
                return True
                
            except Exception as e:
                email_log.status = 'failed'
                email_log.error_message = str(e)
                email_log.save()
                
                logger.error(f"Failed to send email {email_type} to {recipient_email}: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Email service error for {email_type}: {str(e)}")
            return False
    
    @classmethod
    def send_user_email(cls, email_type, user, context=None):
        """
        Send email to a specific user with improved context handling
        """
        if context is None:
            context = {}
        
        # Add user information to context
        user_context = {
            'user_id': user.id,
            'user_email': user.email,
            'user_first_name': user.first_name or '',
            'user_last_name': user.last_name or '',
            'user_full_name': f"{user.first_name} {user.last_name}".strip(),
            'username': user.username,
        }
        
        # Merge contexts
        merged_context = {**context, **user_context}
        
        return cls.send_email(email_type, user.email, merged_context)
    
    @classmethod
    def send_admin_email(cls, email_type, context=None):
        """
        Send email to admin with improved context handling
        """
        return cls.send_email(email_type, cls.ADMIN_EMAIL, context)
    
    @classmethod
    def _clean_context_for_serialization(cls, context):
        """
        Clean context dictionary to ensure all values are JSON serializable
        """
        if not isinstance(context, dict):
            return {}
        
        cleaned = {}
        for key, value in context.items():
            try:
                json.dumps(value)
                cleaned[key] = value
            except (TypeError, ValueError):
                if hasattr(value, '__dict__'):
                    if hasattr(value, 'pk'):
                        cleaned[f"{key}_id"] = value.pk
                    if hasattr(value, 'email'):
                        cleaned[f"{key}_email"] = value.email
                    if hasattr(value, 'name'):
                        cleaned[f"{key}_name"] = str(value.name)
                    cleaned[key] = str(value)
                elif hasattr(value, 'isoformat'):
                    cleaned[key] = value.isoformat()
                else:
                    cleaned[key] = str(value)
                    
                logger.warning(f"Non-serializable value converted for key '{key}': {type(value)}")
        
        return cleaned
    
    @classmethod
    def _render_template_string(cls, template_string, context):
        """
        Safely render a template string with context
        """
        try:
            from django.template import Template, Context
            template = Template(template_string)
            return template.render(Context(context))
        except Exception as e:
            logger.error(f"Template string rendering failed: {str(e)}")
            return template_string 
    
    @classmethod
    def get_email_stats(cls, days=30):
        """
        Get email statistics for the last N days
        """
        from django.utils import timezone
        from django.db.models import Count
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
        stats = EmailLog.objects.filter(
            created_at__gte=start_date
        ).aggregate(
            total=Count('id'),
            sent=Count('id', filter=models.Q(status='sent')),
            failed=Count('id', filter=models.Q(status='failed')),
            pending=Count('id', filter=models.Q(status='pending'))
        )
        
        return stats
    
    @classmethod
    def retry_failed_emails(cls, days=1):
        """
        Retry failed emails from the last N days
        """
        from django.utils import timezone
        from datetime import timedelta
        from .tasks import send_email_task
        
        start_date = timezone.now() - timedelta(days=days)
        
        failed_emails = EmailLog.objects.filter(
            status='failed',
            created_at__gte=start_date
        )
        
        retried_count = 0
        for email_log in failed_emails:
            try:
                send_email_task.delay(
                    email_log.email_type,
                    email_log.recipient_email,
                    email_log.context_data
                )
                retried_count += 1
            except Exception as e:
                logger.error(f"Failed to retry email {email_log.id}: {str(e)}")
        
        return retried_count