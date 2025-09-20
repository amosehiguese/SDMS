from django.db import models
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from .tasks import send_email_task, send_user_email_task
import json

@staff_member_required
def admin_email_sender(request):
    """Admin page to send emails to users"""
    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        recipient_type = request.POST.get('recipient_type')
        
        if not subject or not message:
            messages.error(request, 'Subject and message are required.')
            return redirect('emails:admin_sender')
        
        # Prepare context for email
        context = {
            'subject': subject,
            'message': message,
            'admin_sent': True,
        }
        
        try:
            if recipient_type == 'all':
                # Send to all active users
                users = User.objects.filter(is_active=True)
                count = 0
                for user in users:
                    send_user_email_task.delay('admin_message', user.id, context)
                    count += 1
                    
                messages.success(request, f'Email queued for {count} users.')
                
            elif recipient_type == 'staff':
                # Send to staff users only
                users = User.objects.filter(is_active=True, is_staff=True)
                count = 0
                for user in users:
                    send_user_email_task.delay('admin_message', user.id, context)
                    count += 1
                    
                messages.success(request, f'Email queued for {count} staff members.')
                
            elif recipient_type == 'single':
                # Send to single user by email
                email = request.POST.get('single_email', '').strip()
                if not email:
                    messages.error(request, 'Email address is required for single recipient.')
                    return redirect('emails:admin_sender')
                
                try:
                    user = User.objects.get(email=email, is_active=True)
                    send_user_email_task.delay('admin_message', user.id, context)
                    messages.success(request, f'Email queued for {email}.')
                except User.DoesNotExist:
                    messages.error(request, f'No active user found with email: {email}')
                    return redirect('emails:admin_sender')
                    
            elif recipient_type == 'selected':
                # Send to selected users by IDs
                user_ids = request.POST.getlist('selected_users')
                if not user_ids:
                    messages.error(request, 'No users selected.')
                    return redirect('emails:admin_sender')
                
                count = 0
                for user_id in user_ids:
                    try:
                        user = User.objects.get(id=user_id, is_active=True)
                        send_user_email_task.delay('admin_message', user.id, context)
                        count += 1
                    except User.DoesNotExist:
                        continue
                        
                messages.success(request, f'Email queued for {count} selected users.')
                
            return redirect('emails:admin_sender')
            
        except Exception as e:
            messages.error(request, f'Error sending emails: {str(e)}')
            return redirect('emails:admin_sender')
    
    # GET request - show the form
    users = User.objects.filter(is_active=True).order_by('email')
    
    context = {
        'users': users,
        'total_users': users.count(),
        'staff_users': users.filter(is_staff=True).count(),
    }
    
    return render(request, 'emails/admin_sender.html', context)

@staff_member_required
def search_users_ajax(request):
    """AJAX endpoint to search users"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'users': []})
    
    users = User.objects.filter(
        is_active=True
    ).filter(
        models.Q(email__icontains=query) |
        models.Q(first_name__icontains=query) |
        models.Q(last_name__icontains=query) |
        models.Q(username__icontains=query)
    )[:20]
    
    user_data = []
    for user in users:
        full_name = f"{user.first_name} {user.last_name}".strip()
        display_name = full_name if full_name else user.username
        
        user_data.append({
            'id': user.id,
            'email': user.email,
            'display_name': display_name,
            'is_staff': user.is_staff,
        })
    
    return JsonResponse({'users': user_data})