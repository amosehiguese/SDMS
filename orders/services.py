import logging
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem
from emails.tasks import send_user_email_task, send_admin_email_task
from emails.utils import serialize_for_task, build_order_items_context, build_shipping_context

logger = logging.getLogger(__name__)

class OrderService:
    """Service layer for order operations that need to send emails"""
    
    @classmethod
    @transaction.atomic
    def create_order_from_cart(cls, user, cart, fulfillment_type, shipping_data=None):
        """Create order from cart and send confirmation emails"""
        
        # Create order
        order_data = {
            'user': user,
            'fulfillment_type': fulfillment_type,
            'status': 'pending',
        }
        
        if fulfillment_type == 'deliver' and shipping_data:
            order_data.update({
                'shipping_full_name': shipping_data.get('fullName', ''),
                'shipping_email': shipping_data.get('email', ''),
                'shipping_phone': shipping_data.get('phone', ''),
                'shipping_address': shipping_data.get('address', ''),
            })
        
        order = Order.objects.create(**order_data)
        
        # Create order items
        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                quantity=cart_item.quantity,
                price=cart_item.product.get_display_price()
            )
        
        # Calculate totals
        order.update_totals()
        
        # Clear cart
        cart.clear()
        
        # Send confirmation emails (separate from save)
        cls._send_order_confirmation_emails(order)
        
        return order
    
    @classmethod
    def _send_order_confirmation_emails(cls, order):
        """Send order confirmation emails"""
        try:
            order_items = build_order_items_context(order)
            shipping_context = build_shipping_context(order)
            
            # Get total without triggering save
            total_amount = order.total if order.total else order.calculate_totals()
            
            context = {
                'order_id': serialize_for_task(order.id),
                'order_number': getattr(order, 'order_number', str(order.id)),
                'user_email': order.user.email,
                'user_first_name': order.user.first_name or '',
                'user_last_name': order.user.last_name or '',
                'user_id': serialize_for_task(order.user.id),
                'total_amount': str(total_amount),
                'order_date': order.created_at,
                'items_count': order.items.count(),
                'fulfillment_type': getattr(order, 'fulfillment_type', 'deliver'),
                'status': order.status,
                'order_items': order_items,
                **shipping_context
            }
            
            # Send user confirmation
            send_user_email_task.delay('order_confirmation', order.user.id, context)
            
            # Send admin notification
            admin_context = context.copy()
            admin_context.update({
                'customer_email': order.user.email,
                'customer_name': f"{order.user.first_name} {order.user.last_name}",
                'customer_id': serialize_for_task(order.user.id),
            })
            send_admin_email_task.delay('new_order_admin', admin_context)
            
            logger.info(f"Order confirmation emails queued for order: {order.id}")
            
        except Exception as e:
            logger.error(f"Failed to send order confirmation emails for {order.id}: {e}")
    
    @classmethod
    def update_order_status(cls, order, new_status, **kwargs):
        """Update order status and send appropriate emails"""
        old_status = order.status
        
        if old_status == new_status:
            return order  # No change
        
        # Update order status
        order.status = new_status
        
        # Add status-specific fields
        if new_status == 'shipped' and 'tracking_number' in kwargs:
            order.tracking_number = kwargs['tracking_number']
            order.shipped_at = kwargs.get('shipped_at', timezone.now())
        elif new_status == 'delivered' and 'delivered_at' in kwargs:
            order.delivered_at = kwargs.get('delivered_at', timezone.now())
        
        order.save()
        
        # Send status change emails
        cls._send_status_change_emails(order, old_status, new_status)
        
        return order
    
    @classmethod
    def _send_status_change_emails(cls, order, old_status, new_status):
        """Send status change emails"""
        try:
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
                'total_amount': str(order.total or order.calculate_totals()),
                'updated_at': serialize_for_task(order.updated_at),
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
                from emails.tasks import send_receipt_email_task
                send_receipt_email_task.delay(order.id)
                
            elif new_status == 'liquidated':
                send_user_email_task.delay('asset_liquidation', order.user.id, context)
            
            logger.info(f"Order status change email queued: {old_status} -> {new_status}")
            
        except Exception as e:
            logger.error(f"Failed to send status change emails for {order.id}: {e}")
    
    @classmethod
    def liquidate_order_assets(cls, order, shipping_address):
        """Liquidate held assets and send notification"""
        if order.fulfillment_type == 'hold_asset' and order.status == 'paid':
            order.fulfillment_type = 'deliver'
            order.shipping_address = shipping_address
            order.status = 'paid'  # Keep paid status
            order.update_totals()  # Recalculate with shipping
            order.save()
            
            # Send liquidation email
            cls._send_liquidation_email(order)
            
            return True
        return False
    
    @classmethod
    def _send_liquidation_email(cls, order):
        """Send asset liquidation email"""
        try:
            order_items = build_order_items_context(order)
            
            context = {
                'order_id': serialize_for_task(order.id),
                'order_number': getattr(order, 'order_number', str(order.id)),
                'user_email': order.user.email,
                'user_first_name': order.user.first_name or '',
                'user_last_name': order.user.last_name or '',
                'total_amount': str(order.total or order.calculate_totals()),
                'updated_at': serialize_for_task(order.updated_at),
                'order_items': order_items,
            }
            
            send_user_email_task.delay('asset_liquidation', order.user.id, context)
            logger.info(f"Asset liquidation email queued for order: {order.id}")
            
        except Exception as e:
            logger.error(f"Failed to send liquidation email for {order.id}: {e}")