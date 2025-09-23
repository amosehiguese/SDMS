# Add these new functions to emails/tasks.py

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

@shared_task  
def send_order_confirmation_task(order_id):
    """Send order confirmation email"""
    try:
        from orders.models import Order
        order = Order.objects.select_related('user').get(id=order_id)
        
        order_items = build_order_items_context(order)
        shipping_context = build_shipping_context(order)
        
        context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'user_email': order.user.email,
            'user_first_name': order.user.first_name or '',
            'user_last_name': order.user.last_name or '',
            'user_id': serialize_for_task(order.user.id),
            'total_amount': str(order.calculate_totals()),
            'order_date': order.created_at,
            'items_count': order.items.count(),
            'fulfillment_type': getattr(order, 'fulfillment_type', 'deliver'),
            'status': order.status,
            'order_items': order_items,
            **shipping_context
        }
        
        # Send order confirmation to user
        send_user_email_task.delay('order_confirmation', order.user.id, context)
        
        # Notify admin of new order
        admin_context = {
            'order_id': serialize_for_task(order.id),
            'order_number': getattr(order, 'order_number', str(order.id)),
            'customer_email': order.user.email,
            'customer_name': f"{order.user.first_name} {order.user.last_name}",
            'customer_id': serialize_for_task(order.user.id),
            'total_amount': str(order.calculate_totals()),
            'order_date': order.created_at,
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
            'user_first_name': order.user.first_name or '',
            'user_last_name': order.user.last_name or '',
            'user_id': serialize_for_task(order.user.id),
            'old_status': old_status,
            'new_status': new_status,
            'total_amount': str(order.calculate_totals()),
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
                'shipped_at': order.shipped_at, 
            })
            send_user_email_task.delay('order_shipped', order.user.id, context)
        elif new_status == 'delivered':
            context.update({
                'delivered_at': order.delivered_at,
            })
            send_user_email_task.delay('order_delivered', order.user.id, context)
            # Also send receipt
            send_receipt_email_task.delay(order.id)
        elif new_status == 'liquidated':
            send_user_email_task.delay('asset_liquidation', order.user.id, context)
        
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
            send_receipt_email_task.delay(payment.order.id)
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
        payment = Payment.objects.select_related('order', 'user').get(id=payment_id)
        
        order_context = {}
        if hasattr(payment, 'order') and payment.order:
            order = payment.order
            order_context = {
                'order_id': serialize_for_task(order.id),
                'order_number': getattr(order, 'order_number', str(order.id)),
                'customer_email': order.user.email,
                'customer_name': f"{order.user.first_name} {order.user.last_name}",
                'customer_id': serialize_for_task(order.user.id),
                'order_total': str(order.calculate_totals()),
            }
        
        context = {
            'payment_id': serialize_for_task(payment.id),
            'payment_reference': getattr(payment, 'reference', ''),
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