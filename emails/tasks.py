from celery import shared_task
from django.contrib.auth.models import User

from django.utils import timezone
from .services import EmailService
import logging

logger = logging.getLogger(__name__)

def get_base_context():
    """
    Get base context variables for email templates (reusable across the project)
    Returns only serializable data for Celery tasks
    """
    from django.conf import settings
    from core.models import SiteConfiguration
    from .utils import serialize_for_task
    
    try:
        site_config = SiteConfiguration.get_config()
    except:
        site_config = None
    
    context = {
        'site_name': getattr(site_config, 'site_name', 'Success Direct Marketstore') if site_config else 'Success Direct Marketstore',
        'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
        'contact_email': getattr(site_config, 'contact_email', 'support@successdirectmarketstores.com'),
        'site_logo': 'https://sdmsstore.s3.us-east-1.amazonaws.com/static/img/sdms-logo-w.png',
        'year': timezone.now().year,
        'phone_number': getattr(site_config, 'phone_number', None) if site_config else None,
    }
    
    # Clean context to ensure all values are serializable
    cleaned_context = {}
    for key, value in context.items():
        cleaned_context[key] = serialize_for_task(value)
    
    return cleaned_context

@shared_task(bind=True, max_retries=3)
def send_email_task(self, email_type, recipient_email, context=None):
    """
    Async task to send emails
    
    Args:
        email_type: Type of email to send
        recipient_email: Recipient email address
        context: Dictionary of context variables (all serializable)
    """
    try:
        if context is None:
            context = {}
            
        success = EmailService.send_email(email_type, recipient_email, context)
        if not success:
            raise Exception(f"Failed to send email type: {email_type}")
        return f"Email sent successfully: {email_type} to {recipient_email}"
    except Exception as e:
        logger.error(f"Email task failed: {email_type} to {recipient_email} - {str(e)}")
        # Retry the task
        if self.request.retries < 3:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        raise e

@shared_task(bind=True, max_retries=3)
def send_admin_email_task(self, email_type, context=None):
    """
    Async task to send emails to admin
    
    Args:
        email_type: Type of admin email to send
        context: Dictionary of context variables (all serializable)
    """
    try:
        from .utils import serialize_for_task
        
        if context is None:
            context = {}
        
        # Clean the incoming context to ensure serialization
        cleaned_context = {}
        for key, value in context.items():
            cleaned_context[key] = serialize_for_task(value)
        
        base_context = get_base_context()
        merged_context = {**base_context, **cleaned_context}

        success = EmailService.send_admin_email(email_type, merged_context)
        if not success:
            raise Exception(f"Failed to send admin email type: {email_type}")
        return f"Admin email sent successfully: {email_type}"
    except Exception as e:
        logger.error(f"Admin email task failed: {email_type} - {str(e)}")
        if self.request.retries < 3:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        raise e


@shared_task(bind=True, max_retries=3)
def send_user_email_task(self, email_type, user_id, context=None):
    """
    Async task to send emails to specific user by ID
    
    Args:
        email_type: Type of email to send
        user_id: User ID (not user object)
        context: Dictionary of context variables (all serializable)
    """
    try:
        from .utils import serialize_for_task
        
        # Retrieve user object from ID
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.error(f"User not found for email task: user_id={user_id}")
            raise Exception(f"User with ID {user_id} not found")
        
        if context is None:
            context = {}

        base_context = get_base_context()
        
        # Add user info to context if not already present
        if 'user_email' not in context:
            context['user_email'] = user.email
        if 'user_first_name' not in context:
            context['user_first_name'] = user.first_name or ''
        if 'user_last_name' not in context:
            context['user_last_name'] = user.last_name or ''
        
        # Create user_data dictionary with properly serialized values
        user_data = {
            'user_id': serialize_for_task(user.id),
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'is_active': user.is_active,
            'date_joined': serialize_for_task(user.date_joined) if user.date_joined else None,
        }

        # Clean the incoming context to ensure serialization
        cleaned_context = {}
        for key, value in context.items():
            cleaned_context[key] = serialize_for_task(value)

        # Merge contexts properly
        merged_context = {**base_context, **user_data, **cleaned_context}
        
        success = EmailService.send_user_email(email_type, user, merged_context)
        if not success:
            raise Exception(f"Failed to send user email type: {email_type}")
        return f"User email sent successfully: {email_type} to {user.email}"
        
    except Exception as e:
        logger.error(f"User email task failed: {email_type} for user_id={user_id} - {str(e)}")
        if self.request.retries < 3:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        raise e

@shared_task
def send_bulk_email_task(email_type, recipient_emails, context=None):
    """
    Send bulk emails (useful for newsletters or announcements)
    
    Args:
        email_type: Type of email to send
        recipient_emails: List of email addresses
        context: Dictionary of context variables (all serializable)
    """
    if context is None:
        context = {}
        
    successful = 0
    failed = 0
    
    for email in recipient_emails:
        try:
            success = EmailService.send_email(email_type, email, context)
            if success:
                successful += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Bulk email failed for {email}: {str(e)}")
            failed += 1
    
    return f"Bulk email completed: {successful} successful, {failed} failed"

@shared_task(bind=True, max_retries=3)
def send_receipt_email_task(self, order_id):
    """
    Special task for sending receipt emails with order data retrieval
    
    Args:
        order_id: Order ID (not order object)
    """
    try:
        from orders.models import Order
        
        # Retrieve order object from ID
        try:
            order = Order.objects.select_related('user').prefetch_related('items__product').get(id=order_id)
        except Order.DoesNotExist:
            logger.error(f"Order not found for receipt email: order_id={order_id}")
            raise Exception(f"Order with ID {order_id} not found")
        
        # Build context with serializable data
        context = {
            'order_id': order.id,
            'order_number': getattr(order, 'order_number', str(order.id)),
            'customer_email': order.user.email,
            'customer_name': f"{order.user.first_name} {order.user.last_name}".strip(),
            'customer_first_name': order.user.first_name or '',
            'customer_last_name': order.user.last_name or '',
            'order_date': order.created_at.isoformat(),
            'paid_at': getattr(order, 'paid_at', order.created_at).isoformat(),
            'payment_method': getattr(order, 'payment_method', 'Card'),
            'subtotal': str(getattr(order, 'subtotal', 0)),
            'shipping_cost': str(getattr(order, 'shipping_cost', 0)),
            'tax_amount': str(getattr(order, 'tax_amount', 0)),
            'total': str(order.calculate_totals()),
        }
        
        # Add receipt-specific info if Receipt model exists
        try:
            from orders.models import Receipt
            receipt = Receipt.objects.filter(order=order).first()
            if receipt:
                context['receipt_number'] = getattr(receipt, 'receipt_number', f"RCP-{order.id}")
        except ImportError:
            # Receipt model doesn't exist, generate receipt number
            context['receipt_number'] = f"RCP-{order.id}"
        
        # Add order items as serializable data
        order_items = []
        for item in order.items.all():
            order_items.append({
                'product_title': item.product.title,
                'product_name': getattr(item.product, 'name', item.product.title),
                'quantity': item.quantity,
                'price': str(item.price),
                'total_price': str(item.get_total_price()),
            })
        context['order_items'] = order_items
        
        success = EmailService.send_user_email('receipt', order.user, context)
        if success:
            return f"Receipt email sent for order {order_id}"
        else:
            raise Exception("Failed to send receipt email")
            
    except Exception as e:
        logger.error(f"Receipt email task failed for order {order_id}: {str(e)}")
        if self.request.retries < 3:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        raise e

@shared_task(bind=True, max_retries=3) 
def send_order_status_email_task(self, order_id, email_type, additional_context=None):
    """
    Task for sending order status emails (shipped, delivered, etc.)
    
    Args:
        order_id: Order ID (not order object)
        email_type: Type of status email (order_shipped, order_delivered, etc.)
        additional_context: Additional context data (all serializable)
    """
    try:
        from orders.models import Order
        
        # Retrieve order object from ID
        try:
            order = Order.objects.select_related('user', 'shipping_address').prefetch_related('items__product').get(id=order_id)
        except Order.DoesNotExist:
            logger.error(f"Order not found for status email: order_id={order_id}")
            raise Exception(f"Order with ID {order_id} not found")
        
        # Build base context
        context = {
            'order_id': order.id,
            'order_number': getattr(order, 'order_number', str(order.id)),
            'user_email': order.user.email,
            'user_first_name': order.user.first_name or '',
            'user_last_name': order.user.last_name or '',
            'status': order.status,
            'total': str(order.calculate_totals()),
            'tracking_number': getattr(order, 'tracking_number', ''),
            'shipped_at': order.shipped_at.isoformat() if getattr(order, 'shipped_at', None) else None,
            'delivered_at': order.delivered_at.isoformat() if getattr(order, 'delivered_at', None) else None,
        }
        
        # Add shipping address if available
        if hasattr(order, 'shipping_address') and order.shipping_address:
            context.update({
                'shipping_full_name': getattr(order.shipping_address, 'full_name', ''),
                'shipping_address': getattr(order.shipping_address, 'full_address', ''),
                'shipping_phone': getattr(order.shipping_address, 'phone', ''),
                'shipping_email': getattr(order.shipping_address, 'email', ''),
            })
        
        # Merge additional context
        if additional_context:
            context.update(additional_context)
        
        success = EmailService.send_user_email(email_type, order.user, context)
        if success:
            return f"Order status email sent: {email_type} for order {order_id}"
        else:
            raise Exception(f"Failed to send order status email: {email_type}")
            
    except Exception as e:
        logger.error(f"Order status email task failed: {email_type} for order {order_id}: {str(e)}")
        if self.request.retries < 3:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        raise e