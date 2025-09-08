from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('search/', views.search_products, name='search'),
    path('profile/', views.profile_view, name='profile'),
]
