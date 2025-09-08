from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    # Blog homepage
    path('', views.blog_home, name='home'),
    
    # Post listing and filtering
    path('posts/', views.post_list, name='post_list'),
    path('search/', views.search_posts, name='search'),
    
    # Category and tag filtering
    path('category/<slug:slug>/', views.category_posts, name='category_posts'),
    path('tag/<slug:slug>/', views.tag_posts, name='tag_posts'),
    path('author/<str:username>/', views.author_posts, name='author_posts'),
    
    # Individual post
    path('post/<slug:slug>/', views.post_detail, name='post_detail'),
    
    # Post interactions
    path('post/<slug:slug>/comment/', views.add_comment, name='add_comment'),
    path('post/<slug:slug>/like/', views.like_post, name='like_post'),
]
