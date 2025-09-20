from django.urls import path
from . import views
from .analytics_views import analytics_dashboard, analytics_data, update_order_status, export_analytics


app_name = 'core'

urlpatterns = [
    path('search/', views.search_products, name='search'),
    path('profile/', views.profile_view, name='profile'),
    path('analytics/', analytics_dashboard, name='analytics_dashboard'),
    path('analytics/data/', analytics_data, name='analytics_data'),
    path('analytics/update-order-status/', update_order_status, name='update_order_status'),
    path('analytics/export/', export_analytics, name='export_analytics'),
]

