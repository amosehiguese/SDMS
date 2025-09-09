from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('', views.home, name='home'),
    path('home-products/', views.home_products, name='home_products'),
    path('products/', views.product_list, name='product_list'),
    path('category/<slug:category_slug>/', views.product_list, name='category_products'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('ajax/review/add/<uuid:product_id>/', views.add_review, name='add_review'),
    path('ajax/review/more/<uuid:product_id>/', views.load_more_reviews, name='load_more_reviews'),
    path('ajax/quick-view/<uuid:product_id>/', views.quick_view, name='quick_view'),
    path('help/center/', views.help_center, name='help_center'),
    path('help/shipping/', views.shipping_info, name='shipping_info'),
    path('help/returns/', views.returns_refunds, name='returns_refunds'),
    path('help/size-guide/', views.size_guide, name='size_guide'),
    path('help/track-order/', views.track_order, name='track_order'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
]
