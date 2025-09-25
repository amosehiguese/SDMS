import json
import logging
from datetime import datetime
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from .models import EmailLog  
from django.utils import timezone

logger = logging.getLogger(__name__)

class EmailService:
    """Service for handling all email operations """

    EMAIL_TEMPLATES = {
        'welcome': {
            'subject': 'Welcome to {site_name}!',
            'template': 'emails/user/welcome.html',
        },
        'order_confirmation': {
            'subject': 'Order #{order_number} Confirmed',
            'template': 'emails/user/order_confirmation.html',
        },
        'order_shipped': {
            'subject': 'Order #{order_number} Shipped', 
            'template': 'emails/user/order_shipped.html',
        },
        'order_delivered': {
            'subject': 'Order #{order_number} Delivered',
            'template': 'emails/user/order_delivered.html',
        },
        'receipt': {
            'subject': 'Receipt for Order #{order_number}',
            'template': 'emails/user/receipt.html',
        },
        'asset_liquidation': {
            'subject': 'Asset Liquidation Request Submitted',
            'template': 'emails/user/asset_liquidation.html',
        },
        'sell_item_submitted': {
            'subject': 'Your Item Submission is Under Review',
            'template': 'emails/user/sell_item_submitted.html',
        },
        'sell_item_approved': {
            'subject': 'Your Item Has Been Approved for Sale!',
            'template': 'emails/user/sell_item_approved.html',
        },
        'sell_item_rejected': {
            'subject': 'Item Submission Update',
            'template': 'emails/user/sell_item_rejected.html',
        },
        
        # Admin emails
        'new_order_admin': {
            'subject': 'New Order #{order_number} Received',
            'template': 'emails/admin/new_order.html',
        },
        'new_user_admin': {
            'subject': 'New User Registration: {user_email}',
            'template': 'emails/admin/new_user.html',
        },
        'sell_item_review_admin': {
            'subject': 'New Item Submission Requires Review',
            'template': 'emails/admin/sell_item_review.html',
        },
        'low_stock_admin': {
            'subject': 'Low Stock Alert: {product_title}',
            'template': 'emails/admin/low_stock.html',
        },
        'payment_failed_admin': {
            'subject': 'Payment Failed for Order #{order_number}',
            'template': 'emails/admin/payment_failed.html',
        },
        'asset_liquidation_admin': {
            'subject': 'Asset Liquidation Request Submitted',
            'template': 'emails/admin/asset_liquidation.html',
        },
    }
    
    ADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', 'admin@successdirectmarketstores.com')
    FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@successdirectmarketstores.com')
    
    @classmethod
    def get_email_config(cls, email_type):
        """Get email configuration - now only from code"""
        return cls.EMAIL_TEMPLATES.get(email_type)
    
    @classmethod
    def prepare_context(cls, context):
        """Prepare context with base variables"""
        from .tasks import get_base_context
        
        # Get base context (site info, etc.)
        base_context = get_base_context()
        
        # Merge with provided context
        if context:
            base_context.update(context)
            
        return base_context
    
    @classmethod
    def send_email(cls, email_type, recipient_email, context=None):
        """Send email - simplified without database template lookup"""
        try:
            config = cls.get_email_config(email_type)
            if not config:
                logger.error(f"Email type not configured: {email_type}")
                return False
            
            # Prepare context
            full_context = cls.prepare_context(context or {})
            
            # Render subject using string formatting (much simpler than Django template)
            try:
                subject = config['subject'].format(**full_context)
            except KeyError as e:
                logger.error(f"Missing template variable in subject for {email_type}: {e}")
                logger.error(f"Available variables: {list(full_context.keys())}")
                # Use subject as-is if formatting fails
                subject = config['subject']
            
            # Render HTML template
            try:
                html_content = render_to_string(config['template'], full_context)
                text_content = strip_tags(html_content)
            except Exception as e:
                logger.error(f"Template rendering failed for {email_type}: {str(e)}")
                return False
            
            # Log email attempt
            email_log = EmailLog.objects.create(
                email_type=email_type,
                recipient_email=recipient_email,
                subject=subject,
                status='pending',
                context_data=cls._serialize_context(full_context)
            )
            
            # Send email
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
                email_log.sent_at = timezone.now()
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
        """Send email to specific user"""
        if context is None:
            context = {}
        
        # Add user info to context
        context.update({
            'user_id': user.id,
            'user_email': user.email,
            'user_first_name': user.first_name or '',
            'user_last_name': user.last_name or '',
            'username': user.username,
        })
        
        return cls.send_email(email_type, user.email, context)
    
    @classmethod
    def send_admin_email(cls, email_type, context=None):
        """Send email to admin"""
        return cls.send_email(email_type, cls.ADMIN_EMAIL, context)
    
    @classmethod
    def _serialize_context(cls, context):
        """Serialize context for logging only"""
        from .utils import serialize_for_task
        
        serialized = {}
        for key, value in context.items():
            try:
                serialized[key] = serialize_for_task(value)
            except:
                serialized[key] = str(value)
        return serialized