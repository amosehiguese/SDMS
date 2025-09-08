from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Checkout and payment flow
    path('checkout/', views.checkout, name='checkout'),
    path('initiate/', views.initiate_payment, name='initiate_payment'),
    path('verify/<str:reference>/', views.payment_verification, name='payment_verification'),
    path('status/<str:reference>/', views.payment_status, name='payment_status'),
    
    # Payment history and details
    path('history/', views.payment_history, name='payment_history'),
    path('detail/<str:reference>/', views.payment_detail, name='payment_detail'),
    
    # Payment result pages
    path('success/', views.payment_success, name='payment_success'),
    path('failed/', views.payment_failed, name='payment_failed'),
    
    # Paystack webhook
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
] 