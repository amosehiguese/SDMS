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
        # Only pass serializable data to Celery tasks
        context = {
            'user_email': instance.email,
            'user_first_name': instance.first_name,
            'user_last_name': instance.last_name,
        }
        # Send welcome email to user
        send_user_email_task.delay('welcome', instance.id, context)
        
        # Notify admin of new user
        admin_context = {
            'user_id': str(instance.id),
            'user_email': instance.email,
            'user_first_name': instance.first_name,
            'user_last_name': instance.last_name,
            'user_date_joined': instance.date_joined,
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
    else:
        instance._old_status = None

@receiver(post_save, sender=Order)
def handle_order_status_change(sender, instance, created, **kwargs):
    """Handle order status changes and send appropriate emails"""
    if created:
        return
    
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status
    
    # Only proceed if status actually changed
    if old_status == new_status:
        return
    
    # Only pass serializable data
    context = {
        'order_id': str(instance.id),
        'order_number': instance.order_number,
        'user_email': instance.user.email,
        'order_total': str(instance.total),
        'old_status': old_status,
        'new_status': new_status,
        'fulfillment_type': instance.fulfillment_type,
    }
    
    # Handle different status transitions
    if new_status == 'paid' and old_status != 'paid':
        # Order confirmed - send confirmation email
        send_user_email_task.delay('order_confirmation', instance.user.id, context)
        
        # Send receipt email
        send_receipt_email_task.delay(str(instance.id))
        
        # Notify admin of new paid order
        send_admin_email_task.delay('new_order_admin', context)
        
        logger.info(f"Order confirmation emails queued for order: {instance.order_number}")
    
    elif new_status == 'shipped' and old_status != 'shipped':
        # Order shipped
        shipping_context = {
            **context,
            'tracking_number': instance.tracking_number,
        }
        send_user_email_task.delay('order_shipped', instance.user.id, shipping_context)
        logger.info(f"Order shipped email queued for order: {instance.order_number}")
    
    elif new_status == 'delivered' and old_status != 'delivered':
        # Order delivered
        send_user_email_task.delay('order_delivered', instance.user.id, context)
        logger.info(f"Order delivered email queued for order: {instance.order_number}")

# Payment Signals
@receiver(post_save, sender=Payment)
def handle_payment_status_change(sender, instance, created, **kwargs):
    """Handle payment status changes"""
    if created:
        return
    
    if instance.status == 'failed':
        # Payment failed - notify admin
        context = {
            'payment_id': str(instance.id),
            'payment_reference': instance.payment_reference,
            'order_id': str(instance.order.id),
            'order_number': instance.order.order_number,
            'user_email': instance.user.email,
            'error_message': instance.error_message,
        }
        send_admin_email_task.delay('payment_failed_admin', context)
        logger.info(f"Payment failed email queued for payment: {instance.payment_reference}")

# Sell Item Signals
@receiver(post_save, sender=SellItemSubmission)
def handle_sell_item_submission(sender, instance, created, **kwargs):
    """Handle sell item submission status changes"""
    
    context = {
        'submission_id': str(instance.id),
        'user_id': instance.user.id,
        'user_email': instance.user.email,
        'item_title': instance.title,
        'item_price': str(instance.price),
        'item_quantity': instance.stock_quantity,
    }
    
    if created:
        # New submission - notify user and admin
        send_user_email_task.delay('sell_item_submitted', instance.user.id, context)
        
        admin_context = {
            **context,
            'submission_id': str(instance.id),
        }
        send_admin_email_task.delay('sell_item_review_admin', admin_context)
        
        logger.info(f"Sell item submission emails queued for submission: {instance.id}")
    
    else:
        # Status change
        if hasattr(instance, '_old_status'):
            old_status = instance._old_status
            new_status = instance.status
            
            if old_status != new_status:
                if new_status == 'accepted':
                    # Item approved
                    approval_context = {
                        **context,
                        'admin_notes': instance.admin_notes,
                    }
                    send_user_email_task.delay('sell_item_approved', instance.user.id, approval_context)
                    logger.info(f"Sell item approved email queued for submission: {instance.id}")
                
                elif new_status == 'rejected':
                    # Item rejected
                    rejection_context = {
                        **context,
                        'admin_notes': instance.admin_notes,
                        'rejection_reason': instance.admin_notes,
                    }
                    send_user_email_task.delay('sell_item_rejected', instance.user.id, rejection_context)
                    logger.info(f"Sell item rejected email queued for submission: {instance.id}")

@receiver(pre_save, sender=SellItemSubmission)
def track_sell_item_status_change(sender, instance, **kwargs):
    """Track sell item status changes"""
    if instance.pk:
        try:
            old_instance = SellItemSubmission.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except SellItemSubmission.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

# Product Stock Alerts
@receiver(post_save, sender=OrderItem)
def check_stock_levels(sender, instance, created, **kwargs):
    """Check stock levels after order item creation and send low stock alerts"""
    if created and instance.product.track_stock:
        product = instance.product
        
        # Check if stock is low (less than 10 items)
        if product.stock_quantity <= 10 and product.stock_quantity > 0:
            context = {
                'product_id': str(product.id),
                'product_title': product.title,
                'product_sku': product.sku,
                'stock_quantity': product.stock_quantity,
                'order_id': str(instance.order.id),
                'order_number': instance.order.order_number,
            }
            send_admin_email_task.delay('low_stock_admin', context)
            logger.info(f"Low stock alert queued for product: {product.title}")

# Asset Liquidation Signals
@receiver(post_save, sender=Order)
def handle_asset_liquidation(sender, instance, **kwargs):
    """Handle asset liquidation requests"""
    # This would trigger when an order with held assets gets liquidated
    # You can extend this based on your liquidation workflow
    
    if (hasattr(instance, '_liquidation_requested') and 
        instance._liquidation_requested and 
        instance.fulfillment_type == 'hold_asset'):
        
        context = {
            'order_id': str(instance.id),
            'order_number': instance.order_number,
            'user_id': instance.user.id,
            'user_email': instance.user.email,
        }
        send_user_email_task.delay('asset_liquidation', instance.user.id, context)
        logger.info(f"Asset liquidation email queued for order: {instance.order_number}")