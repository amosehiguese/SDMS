from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Count
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Product, Category, ProductReview

def home(request):
    """Homepage with featured products and flash sales"""
    featured_products = Product.objects.filter(
        is_active=True, 
        is_featured=True
    ).select_related('category').prefetch_related('images')[:8]
    
    flash_sale_products = Product.objects.filter(
        is_active=True,
        flash_sale_enabled=True,
        flash_sale_end_time__gt=timezone.now()
    ).select_related('category').prefetch_related('images')[:12]
    
    categories = Category.objects.filter(is_active=True, parent=None)[:8]
    
    return render(request, 'store/home.html', {
        'featured_products': featured_products,
        'flash_sale_products': flash_sale_products,
        'categories': categories,
    })

def product_list(request, category_slug=None):
    """Product listing with filters"""
    products = Product.objects.filter(is_active=True).select_related('category').prefetch_related('images')
    categories = Category.objects.filter(is_active=True)
    
    # Category filter
    current_category = None
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=current_category)
    
    # Search filter
    search_query = request.GET.get('q')
    if search_query:
        products = products.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Price filter
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)
    
    # Sorting
    sort_by = request.GET.get('sort', 'newest')
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    elif sort_by == 'popular':
        products = products.annotate(review_count=Count('reviews')).order_by('-review_count')
    else:  # newest
        products = products.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        products_data = []
        for product in page_obj:
            image_url = None
            if product.images.exists():
                image_url = product.images.first().image.url
            
            products_data.append({
                'id': str(product.id),
                'title': product.title,
                'slug': product.slug,
                'price': str(product.price),
                'sale_price': str(product.sale_price) if product.sale_price else None,
                'display_price': str(product.get_display_price()),
                'image_url': image_url,
                'category': product.category.name if product.category else '',
                'has_flash_sale': product.has_active_flash_sale(),
                'flash_sale_end_time': product.flash_sale_end_time.isoformat() if product.flash_sale_end_time else None,
                'savings_percentage': product.get_savings_percentage(),
                'is_in_stock': product.is_in_stock(),
            })
        
        return JsonResponse({
            'products': products_data,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'page_number': page_obj.number,
            'total_pages': paginator.num_pages,
        })
    
    return render(request, 'store/product_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'current_category': current_category,
        'search_query': search_query,
        'sort_by': sort_by,
    })

def product_detail(request, slug):
    """Product detail page"""
    product = get_object_or_404(
        Product.objects.select_related('category').prefetch_related('images', 'reviews__user'),
        slug=slug,
        is_active=True
    )
    
    # Get related products
    related_products = Product.objects.filter(
        category=product.category,
        is_active=True
    ).exclude(id=product.id).prefetch_related('images')[:4]
    
    # Get reviews with pagination
    reviews = product.reviews.filter(is_approved=True).select_related('user')
    
    # Calculate average rating
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    
    # Rating distribution
    rating_counts = {}
    for i in range(1, 6):
        rating_counts[i] = reviews.filter(rating=i).count()
    
    return render(request, 'store/product_detail.html', {
        'product': product,
        'related_products': related_products,
        'reviews': reviews[:10],  
        'avg_rating': round(avg_rating, 1),
        'rating_counts': rating_counts,
        'total_reviews': reviews.count(),
    })

@require_http_methods(["POST"])
@login_required
def add_review(request, product_id):
    """AJAX endpoint to add product review"""
    try:
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        # Check if user already reviewed this product
        if ProductReview.objects.filter(product=product, user=request.user).exists():
            return JsonResponse({'success': False, 'error': 'You have already reviewed this product'})
        
        rating = int(request.POST.get('rating', 0))
        title = request.POST.get('title', '').strip()
        comment = request.POST.get('comment', '').strip()
        
        if not (1 <= rating <= 5):
            return JsonResponse({'success': False, 'error': 'Invalid rating'})
        
        if not title or not comment:
            return JsonResponse({'success': False, 'error': 'Title and comment are required'})
        
        # Check if user has purchased this product (for verified purchase)
        from orders.models import Order, OrderItem
        has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            order__status='delivered',
            product=product
        ).exists()
        
        review = ProductReview.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            title=title,
            comment=comment,
            is_verified_purchase=has_purchased
        )
        
        return JsonResponse({
            'success': True,
            'review': {
                'id': str(review.id),
                'rating': review.rating,
                'title': review.title,
                'comment': review.comment,
                'user_email': review.user.email,
                'created_at': review.created_at.strftime('%B %d, %Y'),
                'is_verified_purchase': review.is_verified_purchase,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'An error occurred'})

@require_http_methods(["GET"])
def load_more_reviews(request, product_id):
    """AJAX endpoint to load more reviews"""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    offset = int(request.GET.get('offset', 0))
    limit = 10
    
    reviews = product.reviews.filter(is_approved=True).select_related('user')[offset:offset+limit]
    
    reviews_data = []
    for review in reviews:
        reviews_data.append({
            'id': str(review.id),
            'rating': review.rating,
            'title': review.title,
            'comment': review.comment,
            'user_email': review.user.email,
            'created_at': review.created_at.strftime('%B %d, %Y'),
            'is_verified_purchase': review.is_verified_purchase,
        })
    
    return JsonResponse({
        'reviews': reviews_data,
        'has_more': product.reviews.filter(is_approved=True).count() > offset + limit
    })