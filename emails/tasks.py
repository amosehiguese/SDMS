from celery import shared_task
from django.contrib.auth.models import User
from .services import EmailService
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def send_email_task(self, email_type, recipient_email, context=None):
    """
    Async task to send emails
    
    Args:
        email_type: Type of email to send
        recipient_email: Recipient email address
        context: Dictionary of context variables
    """
    try:
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
    """
    try:
        success = EmailService.send_admin_email(email_type, context)
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
    
    FIXED: Now properly handles user retrieval and context serialization
    """
    try:
        user = User.objects.get(id=user_id)
        
        if context is None:
            context = {}
        
        success = EmailService.send_user_email(email_type, user, context)
        if not success:
            raise Exception(f"Failed to send user email type: {email_type}")
        return f"User email sent successfully: {email_type} to {user.email}"
    except User.DoesNotExist:
        logger.error(f"User not found for email task: user_id={user_id}")
        raise Exception("User not found")
    except Exception as e:
        logger.error(f"User email task failed: {email_type} for user_id={user_id} - {str(e)}")
        if self.request.retries < 3:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        raise e

@shared_task
def send_bulk_email_task(email_type, recipient_emails, context=None):
    """
    Send bulk emails (useful for newsletters or announcements)
    """
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

@shared_task
def send_receipt_email_task(order_id):
    """
    Special task for sending receipt emails with PDF generation
    """
    try:
        from orders.models import Order, Receipt
        
        order = Order.objects.get(id=order_id)
        
        if Receipt:
            # Use Receipt model if available
            receipt = Receipt.objects.filter(order=order).first()
            context = {
                'order': order,
                'receipt': receipt,
                'customer': order.user,
            }
        else:
            # Fallback to basic order information
            context = {
                'order_id': order.id,
                'order_total': str(order.calculate_totals()),
                'customer_email': order.user.email,
                'customer_name': f"{order.user.first_name} {order.user.last_name}",
                'order_date': order.created_at.strftime('%Y-%m-%d'),
            }
        
        success = EmailService.send_user_email('receipt', order.user, context)
        if success:
            return f"Receipt email sent for order {order_id}"
        else:
            raise Exception("Failed to send receipt email")
            
    except Order.DoesNotExist:
        logger.error(f"Order not found for receipt email: order_id={order_id}")
        raise Exception("Order not found")
    except Exception as e:
        logger.error(f"Receipt email task failed for order {order_id}: {str(e)}")
        raise e