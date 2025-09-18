import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from orders.models import Order, OrderItem
from sell_items.models import SellItemSubmission
from payments.models import Payment
from store.models import Product
from .tasks import send_email_task, send_admin_email_task, send_user_email_task, send_receipt_email_task

logger = logging.getLogger(__name__)

# User Registration Signals
@receiver(post_save, sender=User)
def send_welcome_email(sender, instance, created, **kwargs):
    """Send welcome email to new users"""
    if created:
        context = {
            'user_email': instance.email,
            'user_first_name': instance.first_name or '',
            'user_last_name': instance.last_name or '',
        }
        
        # Send welcome email to user - pass user_id instead of user object
        send_user_email_task.delay('welcome', instance.id, context)
        
        # Notify admin of new user
        admin_context = {
            'user_id': instance.id,
            'user_email': instance.email,
            'user_first_name': instance.first_name or '',
            'user_last_name': instance.last_name or '',
            'username': instance.username,
            'user_date_joined': instance.date_joined.isoformat(), 
            'is_active': instance.is_active,
        }
        send_admin_email_task.delay('new_user_admin', admin_context)
        
        logger.info(f"Welcome email queued for user: {instance.email}")

# Order Status Change Signals
@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    """Track order status changes to trigger appropriate emails"""
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Order.DoesNotExist:
            instance._old_status = None

@receiver(post_save, sender=Order)
def send_order_emails(sender, instance, created, **kwargs):
    """Send order-related emails based on order status"""
    
    if created:
        # New order created
        context = {
            'order_id': instance.id,
            'order_number': getattr(instance, 'order_number', str(instance.id)),
            'user_email': instance.user.email,
            'user_first_name': instance.user.first_name or '',
            'user_last_name': instance.user.last_name or '',
            'total_amount': str(instance.calculate_totals()),
            'order_date': instance.created_at.isoformat(),
            'items_count': instance.items.count(),
        }
        
        # Send order confirmation to user
        send_user_email_task.delay('order_confirmation', instance.user.id, context)
        
        # Notify admin of new order
        admin_context = {
            'order_id': instance.id,
            'customer_email': instance.user.email,
            'customer_name': f"{instance.user.first_name} {instance.user.last_name}",
            'total_amount': str(instance.calculate_totals()),
            'order_date': instance.created_at.isoformat(),
            'items_count': instance.items.count(),
        }
        send_admin_email_task.delay('new_order_admin', admin_context)
        
        logger.info(f"Order confirmation email queued for order: {instance.id}")
    
    else:
        # Existing order updated - check for status changes
        old_status = getattr(instance, '_old_status', None)
        
        if old_status and old_status != instance.status:
            context = {
                'order_id': instance.id,
                'order_number': getattr(instance, 'order_number', str(instance.id)),
                'user_email': instance.user.email,
                'user_first_name': instance.user.first_name or '',
                'user_last_name': instance.user.last_name or '',
                'old_status': old_status,
                'new_status': instance.status,
                'total_amount': str(instance.calculate_totals()),
                'updated_at': instance.updated_at.isoformat(),
            }
            
            # Send appropriate email based on new status
            if instance.status == 'shipped':
                send_user_email_task.delay('order_shipped', instance.user.id, context)
            elif instance.status == 'delivered':
                send_user_email_task.delay('order_delivered', instance.user.id, context)
                # Also send receipt
                send_receipt_email_task.delay(instance.id)
            
            logger.info(f"Order status change email queued: {old_status} -> {instance.status}")

# Payment Status Signals
@receiver(post_save, sender=Payment)
def send_payment_emails(sender, instance, created, **kwargs):
    """Send payment-related emails"""
    
    if created and instance.status == 'completed':
        # Payment successful - send receipt
        if hasattr(instance, 'order') and instance.order:
            send_receipt_email_task.delay(instance.order.id)
            logger.info(f"Receipt email queued for payment: {instance.id}")
    
    elif instance.status == 'failed':
        # Payment failed - notify admin
        context = {
            'payment_id': instance.id,
            'payment_reference': getattr(instance, 'reference', ''),
            'amount': str(instance.amount),
            'customer_email': instance.user.email if instance.user else 'Unknown',
            'failed_at': instance.updated_at.isoformat(),
            'error_message': getattr(instance, 'error_message', 'Unknown error'),
        }
        
        send_admin_email_task.delay('payment_failed_admin', context)
        logger.info(f"Payment failure notification queued: {instance.id}")

# Sell Item Submission Signals
@receiver(post_save, sender=SellItemSubmission)
def send_sell_item_emails(sender, instance, created, **kwargs):
    """Send sell item related emails"""
    
    if created:
        # New sell item submission
        context = {
            'submission_id': instance.id,
            'item_name': instance.item_name,
            'user_email': instance.user.email,
            'user_first_name': instance.user.first_name or '',
            'user_last_name': instance.user.last_name or '',
            'asking_price': str(instance.asking_price),
            'submitted_at': instance.created_at.isoformat(),
        }
        
        # Confirm submission to user
        send_user_email_task.delay('sell_item_submitted', instance.user.id, context)
        
        # Notify admin for review
        admin_context = {
            'submission_id': instance.id,
            'item_name': instance.item_name,
            'submitter_email': instance.user.email,
            'submitter_name': f"{instance.user.first_name} {instance.user.last_name}",
            'asking_price': str(instance.asking_price),
            'submitted_at': instance.created_at.isoformat(),
            'category': getattr(instance, 'category', 'Unknown'),
        }
        send_admin_email_task.delay('sell_item_review_admin', admin_context)
        
        logger.info(f"Sell item submission emails queued: {instance.id}")
    
    else:
        # Check for status changes
        old_status = getattr(instance, '_old_status', None)
        
        if old_status and old_status != instance.status:
            context = {
                'submission_id': instance.id,
                'item_name': instance.item_name,
                'user_email': instance.user.email,
                'user_first_name': instance.user.first_name or '',
                'user_last_name': instance.user.last_name or '',
                'old_status': old_status,
                'new_status': instance.status,
                'updated_at': instance.updated_at.isoformat(),
            }
            
            if instance.status == 'approved':
                send_user_email_task.delay('sell_item_approved', instance.user.id, context)
            elif instance.status == 'rejected':
                # Add rejection reason if available
                context['rejection_reason'] = getattr(instance, 'rejection_reason', 'Not specified')
                send_user_email_task.delay('sell_item_rejected', instance.user.id, context)
            
            logger.info(f"Sell item status change email queued: {old_status} -> {instance.status}")

@receiver(pre_save, sender=SellItemSubmission)
def track_sell_item_status_change(sender, instance, **kwargs):
    """Track sell item submission status changes"""
    if instance.pk:
        try:
            old_instance = SellItemSubmission.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except SellItemSubmission.DoesNotExist:
            instance._old_status = None

# Product Low Stock Alerts
@receiver(post_save, sender=Product)
def check_low_stock(sender, instance, **kwargs):
    """Send low stock alerts to admin"""
    
    LOW_STOCK_THRESHOLD = 5
    
    if hasattr(instance, 'stock_quantity') and instance.stock_quantity <= LOW_STOCK_THRESHOLD:
        context = {
            'product_id': instance.id,
            'product_name': instance.name,
            'current_stock': instance.stock_quantity,
            'threshold': LOW_STOCK_THRESHOLD,
            'product_sku': getattr(instance, 'sku', ''),
            'alert_time': instance.updated_at.isoformat(),
        }
        
        send_admin_email_task.delay('low_stock_admin', context)
        logger.info(f"Low stock alert queued for product: {instance.name}")