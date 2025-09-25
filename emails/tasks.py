import logging
from celery import shared_task
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from .utils import serialize_for_task, build_order_items_context, build_shipping_context
from .services import EmailService

logger = logging.getLogger(__name__)

@shared_task
def get_base_context():
    """Get base context for emails (site config, etc.)"""
    try:
        from core.models import SiteConfiguration
        site_config = SiteConfiguration.get_config()
        
        return {
            'site_config': site_config,
            'site_name': getattr(site_config, 'site_name', 'Success Direct Marketstore') if site_config else 'Success Direct Marketstore',
            'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            'contact_email': getattr(site_config, 'contact_email', 'support@successdirectmarketstores.com'),
            'site_logo': 'https://sdmsstore.s3.us-east-1.amazonaws.com/static/img/sdms-logo-w.png',
            'year': timezone.now().year,
            'phone_number': getattr(site_config, 'phone_number', None) if site_config else None,
        }
    except Exception as e:
        logger.error(f"Error getting base context: {str(e)}")
        return {
            'site_name': 'Success Direct MarketStore',
            'site_url': settings.SITE_URL,
            'site_logo': 'https://sdmsstore.s3.us-east-1.amazonaws.com/static/img/sdms-logo-w.png',
            'contact_email': 'support@successdirectmarketstores.com',
            'site_phone': '',
        }

@shared_task
def send_email_task(email_type, recipient_email, context=None):
    """Base task for sending emails"""
    try:
        return EmailService.send_email(email_type, recipient_email, context)
    except Exception as e:
        logger.error(f"Error in send_email_task: {str(e)}")
        return False


@shared_task
def send_user_email_task(email_type, user_id, context=None):
    """Send email to a specific user by user ID"""
    try:
        user = User.objects.get(id=user_id)
        if context is None:
            context = {}
        
        # Add user info to context
        context.update({
            'user_id': serialize_for_task(user.id),
            'user_email': user.email,
            'user_first_name': user.first_name or '',
            'user_last_name': user.last_name or '',
            'username': user.username,
        })
        
        return EmailService.send_email(email_type, user.email, context)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error in send_user_email_task: {str(e)}")
        return False


@shared_task
def send_admin_email_task(email_type, context=None):
    """Send email to admin"""
    try:
        admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@successdirectmarketstores.com')
        return EmailService.send_email(email_type, admin_email, context)
    except Exception as e:
        logger.error(f"Error in send_admin_email_task: {str(e)}")
        return False


@shared_task
def send_bulk_email_task(email_type, recipient_emails, context=None):
    """Send bulk emails to multiple recipients"""
    try:
        success_count = 0
        failed_count = 0
        
        for email in recipient_emails:
            try:
                if EmailService.send_email(email_type, email, context):
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Failed to send bulk email to {email}: {str(e)}")
                failed_count += 1
        
        logger.info(f"Bulk email task completed: {success_count} sent, {failed_count} failed")
        return {'success_count': success_count, 'failed_count': failed_count}
    except Exception as e:
        logger.error(f"Error in send_bulk_email_task: {str(e)}")
        return False


@shared_task
def send_welcome_email_task(user_id):
    """Send welcome email when user registers"""
    try:
        user = User.objects.get(id=user_id)
        context = {
            'user_email': user.email,
            'user_first_name': user.first_name or '',
            'user_last_name': user.last_name or '',
            'user_id': serialize_for_task(user.id),
            'username': user.username,
        }
        
        # Send welcome email to user
        send_user_email_task.delay('welcome', user.id, context)
        
        # Notify admin of new user
        admin_context = {
            'user_id': serialize_for_task(user.id),
            'user_email': user.email,
            'user_first_name': user.first_name or '',
            'user_last_name': user.last_name or '',
            'username': user.username,
            'user_date_joined': serialize_for_task(user.date_joined), 
            'is_active': user.is_active,
        }
        send_admin_email_task.delay('new_user_admin', admin_context)
        
        logger.info(f"Welcome email queued for user: {user.email}")
        return True
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error sending welcome email for user {user_id}: {str(e)}")
        return False


@shared_task
def send_asset_liquidation_task(order_id):
    """Send asset liquidation notification email"""
    try:
        from orders.models import Order
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
        
        order_items = build_order_items_context(order)
        shipping_context = build_shipping_context(order)
        
        context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'user_email': order.user.email,  
            'user_id': serialize_for_task(order.user.id),
            'total_amount': str(order.total),  
            'fulfillment_type': order.fulfillment_type,
            'status': order.status,
            'order_items': order_items,
            **shipping_context  
        }
        
        send_user_email_task.delay('asset_liquidation', order.user.id, context)

        if order.shipping_address:
            customer_name = f"{order.shipping_address.first_name} {order.shipping_address.last_name}".strip()
        else:
            # Fallback to user's name if no shipping address
            user_name = f"{order.user.first_name or ''} {order.user.last_name or ''}".strip()
            customer_name = user_name or order.user.email

        admin_context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'customer_email': order.user.email,
            'customer_name': customer_name,
            'customer_id': serialize_for_task(order.user.id),
            'total_amount': str(order.total),
            'order_items': order_items,
            **shipping_context
        }

        send_admin_email_task.delay('asset_liquidation_admin', admin_context)

        logger.info(f"Asset liquidation email queued for order: {order.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending asset liquidation email: {str(e)}")
        return False

@shared_task  
def send_order_confirmation_task(order_id):
    """Send order confirmation email"""
    try:
        from orders.models import Order
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
        
        order_items = build_order_items_context(order)
        shipping_context = build_shipping_context(order)
        
        context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'user_email': order.user.email,
            'user_id': serialize_for_task(order.user.id),
            'total_amount': str(order.total),
            'order_date': order.created_at,
            'items_count': order.items.count(),
            'fulfillment_type': getattr(order, 'fulfillment_type', 'deliver'),
            'status': order.status,
            'order_items': order_items,
            **shipping_context
        }
        
        # Send order confirmation to user
        send_user_email_task.delay('order_confirmation', order.user.id, context)
        
        if order.shipping_address:
            customer_name = f"{order.shipping_address.first_name} {order.shipping_address.last_name}".strip()
        else:
            # Fallback to user's name if no shipping address
            user_name = f"{order.user.first_name or ''} {order.user.last_name or ''}".strip()
            customer_name = user_name or order.user.email

        # Notify admin of new order
        admin_context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'customer_email': order.user.email,
            'customer_name': customer_name,
            'customer_id': serialize_for_task(order.user.id),
            'total_amount': str(order.total),
            'order_date': serialize_for_task(order.paid_at),
            'items_count': order.items.count(),
            'fulfillment_type': getattr(order, 'fulfillment_type', 'deliver'),
            'status': order.status,
            'order_items': order_items,
            **shipping_context
        }
        send_admin_email_task.delay('new_order_admin', admin_context)
        
        logger.info(f"Order confirmation email queued for order: {order.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending order confirmation for order {order_id}: {str(e)}")
        return False


@shared_task
def send_order_status_update_task(order_id, old_status, new_status):
    """Send email when order status changes"""
    try:
        from orders.models import Order
        order = Order.objects.select_related('user').get(id=order_id)
        
        order_items = build_order_items_context(order)
        shipping_context = build_shipping_context(order)
        
        context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'user_email': order.user.email,
            'user_id': serialize_for_task(order.user.id),
            'old_status': old_status,
            'new_status': new_status,
            'total_amount': str(order.total),
            'updated_at': serialize_for_task(order.updated_at),
            'tracking_number': getattr(order, 'tracking_number', ''),
            'shipped_at': serialize_for_task(order.shipped_at) if getattr(order, 'shipped_at', None) else None,
            'delivered_at': serialize_for_task(order.delivered_at) if getattr(order, 'delivered_at', None) else None,
            'order_items': order_items,
            **shipping_context
        }
        
        # Send appropriate email based on new status
        if new_status == 'shipped':
            context.update({
                'tracking_number': getattr(order, 'tracking_number', ''),
                'shipped_at': serialize_for_task(order.shipped_at), 
            })
            send_user_email_task.delay('order_shipped', order.user.id, context)
        elif new_status == 'delivered':
            context.update({
                'delivered_at': serialize_for_task(order.delivered_at),
            })
            send_user_email_task.delay('order_delivered', order.user.id, context)
            # Also send receipt
            send_receipt_email_task.delay(order.id)

        logger.info(f"Order status change email queued: {old_status} -> {new_status}")
        return True
    except Exception as e:
        logger.error(f"Error sending status update for order {order_id}: {str(e)}")
        return False


@shared_task
def send_payment_success_task(payment_id):
    """Send receipt when payment is successful"""
    try:
        from payments.models import Payment
        payment = Payment.objects.select_related('order').get(id=payment_id)
        
        if hasattr(payment, 'order') and payment.order:
            send_receipt_email_task.delay(str(payment.order.id))
            logger.info(f"Receipt email queued for payment: {payment.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending payment success email for payment {payment_id}: {str(e)}")
        return False


@shared_task
def send_payment_failed_task(payment_id):
    """Send admin notification when payment fails"""
    try:
        from payments.models import Payment
        payment = Payment.objects.select_related('order', 'order__user', 'order__shipping_addres', 'user').get(id=payment_id)
        
        order_context = {}
        if hasattr(payment, 'order') and payment.order:
            order = payment.order

            if order.shipping_address:
                customer_name = f"{order.shipping_address.first_name} {order.shipping_address.last_name}".strip()
            else:
                # Fallback to user's name if no shipping address
                user_name = f"{order.user.first_name or ''} {order.user.last_name or ''}".strip()
                customer_name = user_name or order.user.email

            order_context = {
                'order_id': serialize_for_task(order.id),
                'order_number': getattr(order, 'order_number', str(order.id)),
                'customer_email': order.user.email,
                'customer_name': customer_name,
                'customer_id': serialize_for_task(order.user.id),
                'order_total': str(order.total),
            }
        
        context = {
            'payment_id': serialize_for_task(payment.id),
            'payment_reference': getattr(payment, 'payment_reference', ''),
            'amount': str(payment.amount),
            'customer_email': payment.user.email if payment.user else 'Unknown',
            'customer_id': serialize_for_task(payment.user.id) if payment.user else None,
            'failed_at': serialize_for_task(payment.updated_at),
            'error_message': getattr(payment, 'error_message', 'Unknown error'),
            'error_code': getattr(payment, 'error_code', ''),
            'payment_method': getattr(payment, 'payment_method', ''),
            **order_context
        }
        
        send_admin_email_task.delay('payment_failed_admin', context)
        logger.info(f"Payment failure notification queued: {payment.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending payment failed notification for payment {payment_id}: {str(e)}")
        return False


@shared_task
def send_receipt_email_task(order_id):
    """Send receipt email for completed order"""
    try:
        from orders.models import Order, Receipt
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
        
        order_items = build_order_items_context(order)
        shipping_context = build_shipping_context(order)
        
        receipt, created = Receipt.objects.get_or_create(
            order=order,
            defaults={
                'receipt_data': {
                    'order_id': str(order.id),
                    'amount': str(order.total),
                    'items': order_items,
                    'generated_at': timezone.now().isoformat()
                }
            }
        )

        if order.shipping_address:
            user_first_name = order.shipping_address.first_name
            user_last_name = order.shipping_address.last_name
        else:
            user_first_name = order.user.first_name or ''
            user_last_name = order.user.last_name or ''

        context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'user_email': order.user.email,
            'user_first_name': user_first_name,
            'user_last_name': user_last_name,
            'user_id': serialize_for_task(order.user.id),
            'total_amount': str(order.total),
            'order_date': serialize_for_task(order.created_at),
            'paid_at': serialize_for_task(getattr(order, 'paid_at', order.updated_at)),
            'items_count': order.items.count(),
            'fulfillment_type': getattr(order, 'fulfillment_type', 'deliver'),
            'status': order.status,
            'receipt_number': receipt.receipt_number,  
            'receipt_id': serialize_for_task(receipt.id),
            'order_items': order_items,
            **shipping_context
        }

        receipt.email_sent = True
        receipt.email_sent_at = timezone.now()
        receipt.save(update_fields=['email_sent', 'email_sent_at'])
        
        send_user_email_task.delay('receipt', order.user.id, context)
        logger.info(f"Receipt email queued for order: {order.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending receipt email for order {order_id}: {str(e)}")
        return False


@shared_task
def send_sell_item_notification_task(submission_id):
    """Send email when sell item is submitted"""
    try:
        from sell_items.models import SellItemSubmission
        submission = SellItemSubmission.objects.select_related('user').get(id=submission_id)
        
        # User confirmation
        user_context = {
            'submission_id': serialize_for_task(submission.id),
            'item_name': getattr(submission, 'item_name', ''),
            'title': getattr(submission, 'title', ''),
            'user_email': submission.user.email,
            'user_first_name': submission.user.first_name or '',
            'user_last_name': submission.user.last_name or '',
            'user_id': serialize_for_task(submission.user.id),
            'submitted_at': serialize_for_task(submission.created_at),
            'description': getattr(submission, 'description', ''),
            'price': str(getattr(submission, 'price', 0)),
        }
        send_user_email_task.delay('sell_item_confirmation', submission.user.id, user_context)
        
        # Admin notification
        admin_context = {
            'submission_id': serialize_for_task(submission.id),
            'item_name': getattr(submission, 'item_name', ''),
            'title': getattr(submission, 'title', ''),
            'user_email': submission.user.email,
            'user_first_name': submission.user.first_name or '',
            'user_last_name': submission.user.last_name or '',
            'user_id': serialize_for_task(submission.user.id),
            'submitted_at': serialize_for_task(submission.created_at),
            'description': getattr(submission, 'description', ''),
            'price': str(getattr(submission, 'price', 0)),
        }
        send_admin_email_task.delay('sell_item_review_admin', admin_context)
        
        logger.info(f"Sell item emails queued for submission: {submission.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending sell item notification for submission {submission_id}: {str(e)}")
        return False


@shared_task
def send_low_stock_alert_task(product_id):
    """Send low stock alert to admin"""
    try:
        from store.models import Product
        from core.models import SiteConfiguration
        
        product = Product.objects.get(id=product_id)
        
        # Get threshold from configuration
        try:
            config = SiteConfiguration.get_config()
            low_stock_threshold = config.low_stock_threshold
        except Exception:
            low_stock_threshold = 10  # Fallback
        
        context = {
            'product_id': serialize_for_task(product.id),
            'product_title': product.title,
            'product_slug': product.slug,
            'current_stock': product.stock_quantity,  
            'low_stock_threshold': low_stock_threshold,  
            'track_stock': product.track_stock,
            'allow_backorder': product.allow_backorder,
        }
        
        send_admin_email_task.delay('low_stock_admin', context)
        logger.info(f"Low stock alert queued for product: {product.title}")
        return True
    except Exception as e:
        logger.error(f"Error sending low stock alert for product {product_id}: {str(e)}")
        return False

