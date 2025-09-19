import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from orders.models import Order, OrderItem
from sell_items.models import SellItemSubmission
from payments.models import Payment
from store.models import Product
from .tasks import send_email_task, send_admin_email_task, send_user_email_task, send_receipt_email_task
from .utils import serialize_for_task

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
            'user_id': serialize_for_task(instance.id),
            'username': instance.username,
        }
        
        # Send welcome email to user - pass user_id instead of user object
        send_user_email_task.delay('welcome', instance.id, context)
        
        # Notify admin of new user
        admin_context = {
            'user_id': serialize_for_task(instance.id),
            'user_email': instance.email,
            'user_first_name': instance.first_name or '',
            'user_last_name': instance.last_name or '',
            'username': instance.username,
            'user_date_joined': serialize_for_task(instance.date_joined), 
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
            'order_id': serialize_for_task(instance.id),
            'order_number': getattr(instance, 'order_number', str(instance.id)),
            'user_email': instance.user.email,
            'user_first_name': instance.user.first_name or '',
            'user_last_name': instance.user.last_name or '',
            'user_id': serialize_for_task(instance.user.id),
            'total_amount': str(instance.calculate_totals()),
            'order_date': serialize_for_task(instance.created_at),
            'items_count': instance.items.count(),
            'fulfillment_type': getattr(instance, 'fulfillment_type', 'deliver'),
            'status': instance.status,
        }
        
        # Send order confirmation to user
        send_user_email_task.delay('order_confirmation', instance.user.id, context)
        
        # Notify admin of new order
        admin_context = {
            'order_id': serialize_for_task(instance.id),
            'order_number': getattr(instance, 'order_number', str(instance.id)),
            'customer_email': instance.user.email,
            'customer_name': f"{instance.user.first_name} {instance.user.last_name}",
            'customer_id': serialize_for_task(instance.user.id),
            'total_amount': str(instance.calculate_totals()),
            'order_date': serialize_for_task(instance.created_at),
            'items_count': instance.items.count(),
            'fulfillment_type': getattr(instance, 'fulfillment_type', 'deliver'),
            'status': instance.status,
        }
        send_admin_email_task.delay('new_order_admin', admin_context)
        
        logger.info(f"Order confirmation email queued for order: {instance.id}")
    
    else:
        # Existing order updated - check for status changes
        old_status = getattr(instance, '_old_status', None)
        
        if old_status and old_status != instance.status:
            context = {
                'order_id': serialize_for_task(instance.id),
                'order_number': getattr(instance, 'order_number', str(instance.id)),
                'user_email': instance.user.email,
                'user_first_name': instance.user.first_name or '',
                'user_last_name': instance.user.last_name or '',
                'user_id': serialize_for_task(instance.user.id),
                'old_status': old_status,
                'new_status': instance.status,
                'total_amount': str(instance.calculate_totals()),
                'updated_at': serialize_for_task(instance.updated_at),
                'tracking_number': getattr(instance, 'tracking_number', ''),
                'shipped_at': serialize_for_task(instance.shipped_at) if getattr(instance, 'shipped_at', None) else None,
                'delivered_at': serialize_for_task(instance.delivered_at) if getattr(instance, 'delivered_at', None) else None,
            }
            
            # Send appropriate email based on new status
            if instance.status == 'shipped':
                send_user_email_task.delay('order_shipped', instance.user.id, context)
            elif instance.status == 'delivered':
                send_user_email_task.delay('order_delivered', instance.user.id, context)
                # Also send receipt
                send_receipt_email_task.delay(instance.id)
            elif instance.status == 'liquidated':
                send_user_email_task.delay('asset_liquidation', instance.user.id, context)
            
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
        order_context = {}
        if hasattr(instance, 'order') and instance.order:
            order = instance.order
            order_context = {
                'order_id': serialize_for_task(order.id),
                'order_number': getattr(order, 'order_number', str(order.id)),
                'customer_email': order.user.email,
                'customer_name': f"{order.user.first_name} {order.user.last_name}",
                'customer_id': serialize_for_task(order.user.id),
                'order_total': str(order.calculate_totals()),
            }
        
        context = {
            'payment_id': serialize_for_task(instance.id),
            'payment_reference': getattr(instance, 'reference', ''),
            'amount': str(instance.amount),
            'customer_email': instance.user.email if instance.user else 'Unknown',
            'customer_id': serialize_for_task(instance.user.id) if instance.user else None,
            'failed_at': serialize_for_task(instance.updated_at),
            'error_message': getattr(instance, 'error_message', 'Unknown error'),
            'error_code': getattr(instance, 'error_code', ''),
            'payment_method': getattr(instance, 'payment_method', ''),
            **order_context  # Merge order context
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
            'submission_id': serialize_for_task(instance.id),
            'item_name': getattr(instance, 'item_name', ''),
            'title': getattr(instance, 'title', ''),
            'user_email': instance.user.email,
            'user_first_name': instance.user.first_name or '',
            'user_last_name': instance.user.last_name or '',
            'user_id': serialize_for_task(instance.user.id),
            'asking_price': str(getattr(instance, 'asking_price', 0)),
            'price': str(getattr(instance, 'price', 0)),
            'stock_quantity': getattr(instance, 'stock_quantity', 0),
            'source': getattr(instance, 'source', ''),
            'description': getattr(instance, 'description', ''),
            'submitted_at': serialize_for_task(instance.created_at),
            'category_name': instance.category.name if getattr(instance, 'category', None) else 'Uncategorized',
            'has_complete_bank_details': getattr(instance, 'has_complete_bank_details', False),
            'bank_name': getattr(instance, 'bank_name', ''),
            'account_number': getattr(instance, 'account_number', ''),
            'account_holder_name': getattr(instance, 'account_holder_name', ''),
        }
        
        # Add held asset order info if available
        if hasattr(instance, 'held_asset_order') and instance.held_asset_order:
            context.update({
                'held_asset_order_id': serialize_for_task(instance.held_asset_order.id),
                'held_asset_order_number': getattr(instance.held_asset_order, 'order_number', str(instance.held_asset_order.id)),
                'held_asset_order_date': serialize_for_task(instance.held_asset_order.created_at),
                'max_allowed_quantity': getattr(instance, 'max_allowed_quantity', 0),
            })
        
        # Confirm submission to user
        send_user_email_task.delay('sell_item_submitted', instance.user.id, context)
        
        # Notify admin for review
        admin_context = {
            'submission_id': serialize_for_task(instance.id),
            'item_name': getattr(instance, 'item_name', ''),
            'title': getattr(instance, 'title', ''),
            'submitter_email': instance.user.email,
            'submitter_name': f"{instance.user.first_name} {instance.user.last_name}",
            'submitter_id': serialize_for_task(instance.user.id),
            'asking_price': str(getattr(instance, 'asking_price', 0)),
            'price': str(getattr(instance, 'price', 0)),
            'stock_quantity': getattr(instance, 'stock_quantity', 0),
            'source': getattr(instance, 'source', ''),
            'description': getattr(instance, 'description', ''),
            'submitted_at': serialize_for_task(instance.created_at),
            'category_name': instance.category.name if getattr(instance, 'category', None) else 'Uncategorized',
            'has_complete_bank_details': getattr(instance, 'has_complete_bank_details', False),
            'bank_name': getattr(instance, 'bank_name', ''),
            'account_number': getattr(instance, 'account_number', ''),
            'account_holder_name': getattr(instance, 'account_holder_name', ''),
        }
        
        # Add held asset order info for admin too
        if hasattr(instance, 'held_asset_order') and instance.held_asset_order:
            admin_context.update({
                'held_asset_order_id': serialize_for_task(instance.held_asset_order.id),
                'held_asset_order_number': getattr(instance.held_asset_order, 'order_number', str(instance.held_asset_order.id)),
                'held_asset_order_date': serialize_for_task(instance.held_asset_order.created_at),
                'max_allowed_quantity': getattr(instance, 'max_allowed_quantity', 0),
            })
        
        send_admin_email_task.delay('sell_item_review_admin', admin_context)
        
        logger.info(f"Sell item submission emails queued: {instance.id}")
    
    else:
        # Check for status changes
        old_status = getattr(instance, '_old_status', None)
        
        if old_status and old_status != instance.status:
            context = {
                'submission_id': serialize_for_task(instance.id),
                'item_name': getattr(instance, 'item_name', ''),
                'title': getattr(instance, 'title', ''),
                'user_email': instance.user.email,
                'user_first_name': instance.user.first_name or '',
                'user_last_name': instance.user.last_name or '',
                'user_id': serialize_for_task(instance.user.id),
                'old_status': old_status,
                'new_status': instance.status,
                'updated_at': serialize_for_task(instance.updated_at),
                'price': str(getattr(instance, 'price', 0)),
                'stock_quantity': getattr(instance, 'stock_quantity', 0),
                'reviewed_at': instance.updated_at.isoformat(),
                'admin_notes': getattr(instance, 'admin_notes', ''),
                'rejection_reason': getattr(instance, 'rejection_reason', 'Not specified'),
            }
            
            if instance.status == 'approved':
                send_user_email_task.delay('sell_item_approved', instance.user.id, context)
            elif instance.status == 'rejected':
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
            'product_id': serialize_for_task(instance.id),
            'product_name': getattr(instance, 'name', ''),
            'product_title': getattr(instance, 'title', ''),
            'current_stock': getattr(instance, 'stock_quantity', 0),
            'threshold': LOW_STOCK_THRESHOLD,
            'product_sku': getattr(instance, 'sku', ''),
            'alert_time': serialize_for_task(instance.updated_at),
            'price': str(getattr(instance, 'price', 0)),
            'is_active': getattr(instance, 'is_active', False),
            'category_name': instance.category.name if getattr(instance, 'category', None) else 'Uncategorized',
        }
        
        send_admin_email_task.delay('low_stock_admin', context)
        logger.info(f"Low stock alert queued for product: {getattr(instance, 'name', instance.id)}")