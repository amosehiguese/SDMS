from django.urls import path
from . import views

app_name = 'emails'

urlpatterns = [
    path('admin/sender/', views.admin_email_sender, name='admin_sender'),
    path('admin/search-users/', views.search_users_ajax, name='search_users'),
]