from django.urls import path
from . import views

app_name = 'sell_items'

urlpatterns = [
    # User selling pages
    path('sell/', views.sell_item_list, name='sell_item_list'),
    path('sell/submit/', views.submit_sell_item, name='submit_sell_item'),
    path('sell/submit/held-asset/<uuid:order_id>/', views.submit_held_asset_sell, name='submit_held_asset_sell'),
    path('sell/detail/<uuid:submission_id>/', views.sell_submission_detail, name='sell_submission_detail'),
    path('sell/bank-details/<uuid:submission_id>/', views.update_bank_details, name='update_bank_details'),
    path('sell/edit/<uuid:submission_id>/', views.edit_sell_submission, name='edit_sell_submission'),
    
    # Admin review pages
    path('admin/submissions/', views.admin_submissions, name='admin_submissions'),
    path('admin/review/<uuid:submission_id>/', views.admin_review_submission, name='admin_review_submission'),
    path('ajax/admin/update-status/', views.update_submission_status, name='update_submission_status'),
    path('ajax/admin/create-product/', views.create_product_from_submission, name='create_product_from_submission'),
]