from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # Cart URLs
    path('cart/', views.cart_view, name='cart'),
    path('ajax/cart/', views.cart_sidebar, name='cart_sidebar'),
    path('ajax/cart/add/', views.add_to_cart, name='add_to_cart'),
    path('ajax/cart/update/', views.update_cart_item, name='update_cart_item'),
    path('ajax/cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('ajax/cart/count/', views.get_cart_count, name='get_cart_count'),
    
    # Checkout URLs
    path('checkout/', views.checkout, name='checkout'),
    path('ajax/create-order/', views.create_order, name='create_order'),
    
    # Order management URLs
    path('order/<uuid:order_id>/', views.order_detail, name='order_detail'),
    path('history/', views.order_history, name='order_history'),
    
    # Held assets URLs
    path('held-assets/', views.held_assets, name='held_assets'),
    path('ajax/liquidate/<uuid:order_id>/', views.liquidate_asset, name='liquidate_asset'),
    
    # Shipping addresses URLs
    path('addresses/', views.shipping_addresses, name='shipping_addresses'),
    path('ajax/addresses/', views.get_shipping_addresses, name='get_shipping_addresses'),
    path('ajax/address/add/', views.add_shipping_address, name='add_shipping_address'),
    path('ajax/address/get/<uuid:address_id>/', views.get_shipping_address, name='get_shipping_address'),
    path('ajax/address/edit/<uuid:address_id>/', views.edit_shipping_address, name='edit_shipping_address'),
    path('ajax/address/set-default/<uuid:address_id>/', views.set_default_address, name='set_default_address'),
    path('order/<uuid:order_id>/receipt/', views.order_receipt, name='order_receipt'),
    path('ajax/order/cancel/<uuid:order_id>/', views.cancel_order, name='cancel_order'),
    path('ajax/address/delete/<uuid:address_id>/', views.delete_shipping_address, name='delete_shipping_address'),
]