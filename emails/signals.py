import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from emails.tasks import send_admin_email_task, send_user_email_task
from emails.utils import serialize_for_task

logger = logging.getLogger(__name__)

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