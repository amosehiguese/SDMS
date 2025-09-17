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
    """
    try:
        user = User.objects.get(id=user_id)
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
    from orders.models import Order, Receipt
    from django.utils import timezone
    
    try:
        order = Order.objects.get(id=order_id)
        receipt, created = Receipt.objects.get_or_create(order=order)
        
        # Generate receipt data if needed
        if not receipt.receipt_data:
            receipt.receipt_data = {
                'order_number': order.order_number,
                'total': str(order.total),
                'items': [
                    {
                        'title': item.product.title,
                        'quantity': item.quantity,
                        'price': str(item.price),
                        'total': str(item.get_total_price())
                    }
                    for item in order.items.all()
                ],
                'payment_date': order.paid_at.isoformat() if order.paid_at else None,
            }
            receipt.save()
        
        # Send receipt email
        context = {
            'order_id': str(order.id),
            'receipt_id': str(receipt.id),
            'receipt_data': receipt.receipt_data
        }
        
        success = EmailService.send_user_email('receipt', order.user, context)
        
        if success:
            receipt.email_sent = True
            receipt.email_sent_at = timezone.now()
            receipt.save()
        
        return f"Receipt email sent for order {order.order_number}"
        
    except Order.DoesNotExist:
        logger.error(f"Order not found for receipt email: order_id={order_id}")
        raise Exception("Order not found")
    except Exception as e:
        logger.error(f"Receipt email task failed for order_id={order_id}: {str(e)}")
        raise e