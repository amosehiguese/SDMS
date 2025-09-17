import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from core.models import SiteConfiguration
from .models import EmailTemplate, EmailLog

logger = logging.getLogger(__name__)

class EmailService:
    """Centralized email service for all application emails"""
    
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
    }
    
    @classmethod
    def get_email_config(cls, email_type):
        """Get email configuration from database or defaults"""
        try:
            template = EmailTemplate.objects.get(email_type=email_type, is_active=True)
            return {
                'subject': template.subject,
                'template': template.template_path,
                'recipient_type': template.recipient_type
            }
        except EmailTemplate.DoesNotExist:
            return cls.DEFAULT_TEMPLATES.get(email_type, {})
    
    @classmethod
    def prepare_context(cls, context, email_type):
        """Prepare email context with site configuration and common variables"""
        site_config = SiteConfiguration.get_config()
        
        base_context = {
            'site_name': site_config.site_name,
            'site_logo': site_config.site_logo,
            'site_url': settings.SITE_URL,
            'contact_email': site_config.contact_email,
            'phone_number': site_config.phone_number,
            'year': timezone.now().year,
        }
        
        # If we have object IDs in context, fetch the actual objects
        if 'user_id' in context:
            try:
                from django.contrib.auth.models import User
                user = User.objects.get(id=context['user_id'])
                base_context['user'] = user
            except User.DoesNotExist:
                pass
                
        if 'order_id' in context:
            try:
                from orders.models import Order
                order = Order.objects.get(id=context['order_id'])
                base_context['order'] = order
            except:
                pass
                
        if 'product_id' in context:
            try:
                from store.models import Product
                product = Product.objects.get(id=context['product_id'])
                base_context['product'] = product
            except:
                pass
                
        if 'submission_id' in context:
            try:
                from sell_items.models import SellItemSubmission
                submission = SellItemSubmission.objects.get(id=context['submission_id'])
                base_context['submission'] = submission
            except:
                pass
        
        base_context.update(context)
        return base_context
    
    @classmethod
    def get_admin_email(cls):
        """Get admin email address"""
        site_config = SiteConfiguration.get_config()
        return getattr(settings, 'ADMIN_EMAIL', site_config.contact_email)
    
    @classmethod
    def send_email(cls, email_type, recipient_email, context=None):
        """
        Send email using configuration and context
        
        Args:
            email_type: Type of email to send
            recipient_email: Recipient email address
            context: Dictionary of context variables for template
        """
        if context is None:
            context = {}
            
        # Get email configuration
        config = cls.get_email_config(email_type)
        if not config:
            logger.error(f"No email configuration found for type: {email_type}")
            return False
            
        # Prepare context
        full_context = cls.prepare_context(context, email_type)
        
        # Create email log entry
        email_log = EmailLog.objects.create(
            email_type=email_type,
            recipient_email=recipient_email,
            subject=config['subject'].format(**full_context),
            context_data=context
        )
        
        try:
            # Render email content
            html_content = render_to_string(config['template'], full_context)
            subject = config['subject'].format(**full_context)
            
            # Send email
            send_mail(
                subject=subject,
                message='',  # We're using HTML content
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                html_message=html_content,
                fail_silently=False
            )
            
            # Update log
            email_log.status = 'sent'
            email_log.sent_at = timezone.now()
            email_log.save()
            
            logger.info(f"Email sent successfully: {email_type} to {recipient_email}")
            return True
            
        except Exception as e:
            # Log error
            error_msg = str(e)
            email_log.status = 'failed'
            email_log.error_message = error_msg
            email_log.save()
            
            logger.error(f"Failed to send email {email_type} to {recipient_email}: {error_msg}")
            return False
    
    @classmethod
    def send_admin_email(cls, email_type, context=None):
        """Send email to admin"""
        admin_email = cls.get_admin_email()
        return cls.send_email(email_type, admin_email, context)
    
    @classmethod
    def send_user_email(cls, email_type, user, context=None):
        """Send email to user"""
        if context is None:
            context = {}
        context['user'] = user
        return cls.send_email(email_type, user.email, context)