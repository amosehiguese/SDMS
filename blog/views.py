from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, F
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.db.models.functions import TruncMonth
from .models import BlogPost, BlogCategory, BlogTag, BlogComment, BlogPostView

def blog_home(request):
    """Blog homepage with featured posts and categories"""
    featured_posts = BlogPost.objects.filter(
        status='published',
        featured=True
    ).select_related('author', 'category').prefetch_related('tags')[:6]
    
    recent_posts = BlogPost.objects.filter(
        status='published'
    ).select_related('author', 'category').prefetch_related('tags')[:8]
    
    categories = BlogCategory.objects.filter(
        is_active=True
    ).annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0)[:8]
    
    popular_tags = BlogTag.objects.annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0).order_by('-post_count')[:10]
    
    context = {
        'featured_posts': featured_posts,
        'recent_posts': recent_posts,
        'categories': categories,
        'popular_tags': popular_tags,
    }
    return render(request, 'blog/home.html', context)

def post_list(request):
    """List all published blog posts with filtering and pagination"""
    posts = BlogPost.objects.filter(
        status='published'
    ).select_related('author', 'category').prefetch_related('tags')
    
    # Category filter
    category_slug = request.GET.get('category')
    if category_slug:
        category = get_object_or_404(BlogCategory, slug=category_slug, is_active=True)
        posts = posts.filter(category=category)
    else:
        category = None
    
    # Tag filter
    tag_slug = request.GET.get('tag')
    if tag_slug:
        tag = get_object_or_404(BlogTag, slug=tag_slug)
        posts = posts.filter(tags=tag)
    else:
        tag = None
    
    # Search filter
    search_query = request.GET.get('q')
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(excerpt__icontains=search_query) |
            Q(content__icontains=search_query)
        )
    
    # Author filter
    author_id = request.GET.get('author')
    if author_id:
        posts = posts.filter(author_id=author_id)
    
    # Sorting
    sort_by = request.GET.get('sort', 'newest')
    if sort_by == 'oldest':
        posts = posts.order_by('published_at')
    elif sort_by == 'popular':
        posts = posts.order_by('-view_count')
    elif sort_by == 'most_liked':
        posts = posts.order_by('-like_count')
    else:  # newest
        posts = posts.order_by('-published_at')
    
    # Pagination
    paginator = Paginator(posts, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get filter options
    categories = BlogCategory.objects.filter(is_active=True).annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0)
    
    tags = BlogTag.objects.annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0).order_by('-post_count')[:20]
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'tags': tags,
        'current_category': category,
        'current_tag': tag,
        'search_query': search_query,
        'sort_by': sort_by,
    }
    return render(request, 'blog/post_list.html', context)

def post_detail(request, slug):
    """Blog post detail view with comments"""
    post = get_object_or_404(
        BlogPost.objects.select_related('author', 'category').prefetch_related('tags'),
        slug=slug,
        status='published'
    )
    
    # Track view
    if request.user.is_authenticated:
        BlogPostView.objects.get_or_create(
            post=post,
            user=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referer=request.META.get('HTTP_REFERER', ''),
            defaults={'created_at': timezone.now()}
        )
    else:
        BlogPostView.objects.get_or_create(
            post=post,
            user=None,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referer=request.META.get('HTTP_REFERER', ''),
            defaults={'created_at': timezone.now()}
        )
    
    # Increment view count
    post.increment_view_count()
    
    # Get comments
    comments = post.comments.filter(is_approved=True, parent=None).select_related('author')
    
    # Get related posts
    related_posts = BlogPost.objects.filter(
        status='published',
        category=post.category
    ).exclude(id=post.id).select_related('author', 'category')[:4]
    
    context = {
        'post': post,
        'comments': comments,
        'related_posts': related_posts,
    }
    return render(request, 'blog/post_detail.html', context)

def category_posts(request, slug):
    """Posts filtered by category"""
    category = get_object_or_404(BlogCategory, slug=slug, is_active=True)
    posts = BlogPost.objects.filter(
        status='published',
        category=category
    ).select_related('author', 'category').prefetch_related('tags')
    
    # Pagination
    paginator = Paginator(posts, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'category': category,
    }
    return render(request, 'blog/category_posts.html', context)

def tag_posts(request, slug):
    """Posts filtered by tag"""
    tag = get_object_or_404(BlogTag, slug=slug)
    posts = BlogPost.objects.filter(
        status='published',
        tags=tag
    ).select_related('author', 'category').prefetch_related('tags')
    
    # Pagination
    paginator = Paginator(posts, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'tag': tag,
    }
    return render(request, 'blog/tag_posts.html', context)

@login_required
@require_http_methods(["POST"])
def add_comment(request, slug):
    """Add a comment to a blog post"""
    post = get_object_or_404(BlogPost, slug=slug, status='published')
    
    content = request.POST.get('content', '').strip()
    parent_id = request.POST.get('parent_id')
    
    if not content:
        messages.error(request, 'Comment content cannot be empty.')
        return redirect('blog:post_detail', slug=slug)
    
    # Create comment
    comment = BlogComment.objects.create(
        post=post,
        author=request.user,
        content=content,
        parent_id=parent_id if parent_id else None
    )
    
    messages.success(request, 'Your comment has been submitted for review.')
    return redirect('blog:post_detail', slug=slug)

@login_required
@require_http_methods(["POST"])
def like_post(request, slug):
    """Like/unlike a blog post"""
    post = get_object_or_404(BlogPost, slug=slug, status='published')
    
    # This is a simple implementation - you might want to use a separate Like model
    # to track individual user likes and prevent duplicate likes
    post.like_count += 1
    post.save(update_fields=['like_count'])
    
    return JsonResponse({
        'success': True,
        'like_count': post.like_count
    })

def search_posts(request):
    """Search blog posts"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return redirect('blog:post_list')
    
    posts = BlogPost.objects.filter(
        status='published'
    ).filter(
        Q(title__icontains=query) |
        Q(excerpt__icontains=query) |
        Q(content__icontains=query)
    ).select_related('author', 'category').prefetch_related('tags')
    
    # Pagination
    paginator = Paginator(posts, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': query,
    }
    return render(request, 'blog/search_results.html', context)

def author_posts(request, username):
    """Posts by a specific author"""
    posts = BlogPost.objects.filter(
        status='published',
        author__username=username
    ).select_related('author', 'category').prefetch_related('tags')
    
    if not posts.exists():
        # Check if author exists
        from django.contrib.auth.models import User
        author = User.objects.filter(username=username).first()
        if not author:
            return render(request, 'blog/author_not_found.html', {'username': username})
    
    # Pagination
    paginator = Paginator(posts, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'author_username': username,
    }
    return render(request, 'blog/author_posts.html', context)
