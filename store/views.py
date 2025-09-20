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

def home_products(request):
    page = int(request.GET.get('page', 1))
    category_name = request.GET.get('category')

    # Start with all active products
    products = Product.objects.filter(is_active=True).select_related('category').prefetch_related('images')

    # If a category is chosen, filter by it
    if category_name:
        products = products.filter(category__name__iexact=category_name)
    else:
        # No category: order with featured first, then others
        products = products.order_by('-is_featured', '-id')  # adjust ordering as needed

    paginator = Paginator(products, 20)
    page_obj = paginator.get_page(page)

    products_html = ''
    for product in page_obj:
        image_url = product.images.first().image.url if product.images.exists() else None
        products_html += f'''
        <div class="product-card bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow group">
            <div class="relative">
                {f'<img src="{image_url}" alt="{product.title}" class="w-full h-48 object-cover group-hover:scale-105 transition-transform">' if image_url else '<div class="w-full h-48 bg-gray-200 flex items-center justify-center"><i class="fas fa-image text-gray-400 text-3xl"></i></div>'}
                {f'<div class="absolute top-2 left-2 bg-red-600 text-white px-2 py-1 rounded text-xs font-bold"><i class="fas fa-bolt"></i> {product.get_savings_percentage()}% OFF</div>' if product.has_active_flash_sale() else ''}
                <button onclick="addToCart('{product.id}')" class="absolute bottom-2 right-2 bg-amber-700 text-white p-2 rounded-full opacity-0 group-hover:opacity-100 transition">
                    <i class="fas fa-shopping-cart"></i>
                </button>
            </div>
            <div class="p-4">
                <a href="/product/{product.slug}/" class="block">
                    <h3 class="font-semibold mb-2 hover:text-amber-700 transition-colors line-clamp-2">{product.title}</h3>
                    {f'<p class="text-gray-500 text-xs mb-2">{product.category.name}</p>' if product.category else ''}
                    <div class="flex items-center justify-between mb-3">
                        <div>
                            {f'<span class="text-lg font-bold text-amber-700">₦{product.get_display_price()}</span><span class="text-gray-500 line-through text-sm ml-1">₦{product.price}</span>' if product.sale_price else f'<span class="text-lg font-bold text-amber-700">₦{product.get_display_price()}</span>'}
                        </div>
                    </div>
                </a>
            </div>
        </div>
        '''

    return JsonResponse({
        'products_html': products_html,
        'has_next': page_obj.has_next(),
        'page_number': page_obj.number,
        'total_pages': paginator.num_pages,
    })




def product_list(request, category_slug=None):
    """Product listing with filters"""
    # Get search query from URL parameters
    search_query = request.GET.get('search', '').strip()
    
    products = Product.objects.filter(is_active=True).select_related('category').prefetch_related('images')
    categories = Category.objects.filter(is_active=True)

    current_category = None
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=current_category)

    # Apply search filter
    if search_query:
        products = products.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )
    
    # Additional filters
    category_id = request.GET.get('category')
    if category_id:
        try:
            products = products.filter(category_id=int(category_id))
        except (ValueError, TypeError):
            pass
    
    # Price filter
    price_range = request.GET.get('price')
    if price_range:
        if price_range == '0-10000':
            products = products.filter(price__lte=10000)
        elif price_range == '10000-50000':
            products = products.filter(price__gte=10000, price__lte=50000)
        elif price_range == '50000-100000':
            products = products.filter(price__gte=50000, price__lte=100000)
        elif price_range == '100000-':
            products = products.filter(price__gte=100000)
    
    # Sorting
    sort_by = request.GET.get('sort', 'name')
    if sort_by == 'name':
        products = products.order_by('title')
    elif sort_by == '-name':
        products = products.order_by('-title')
    elif sort_by == 'price':
        products = products.order_by('price')
    elif sort_by == '-price':
        products = products.order_by('-price')
    elif sort_by == '-created_at':
        products = products.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(products, 2)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Handle AJAX requests for filtering
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        products_html = generate_product_cards_html(page_obj)
        
        return JsonResponse({
            'products_html': products_html,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'page_number': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_products': paginator.count,
        })
    
    return render(request, 'store/product_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'current_category': current_category,
        'search_query': search_query,
        'total_products': paginator.count,
    })


def generate_product_cards_html(page_obj):
    """Helper function to generate product cards HTML"""
    products_html = ''
    for product in page_obj:
        image_url = None
        if product.images.exists():
            image_url = product.images.first().image.url
        
        flash_sale_badge = ''
        if product.has_active_flash_sale():
            flash_sale_badge = f'<div class="absolute top-2 left-2 bg-red-600 text-white px-2 py-1 rounded text-xs font-bold"><i class="fas fa-bolt"></i> {product.get_savings_percentage()}% OFF</div>'
        
        image_html = f'<img src="{image_url}" alt="{product.title}" class="w-full h-48 object-cover group-hover:scale-105 transition-transform">' if image_url else '<div class="w-full h-48 bg-gray-200 flex items-center justify-center"><i class="fas fa-image text-gray-400 text-3xl"></i></div>'
        
        category_html = f'<p class="text-gray-500 text-xs mb-2">{product.category.name}</p>' if product.category else ''
        
        price_html = f'<span class="text-lg font-bold text-amber-700">₦{product.get_display_price()}</span>'
        if product.sale_price:
            price_html += f'<span class="text-gray-500 line-through text-sm ml-1">₦{product.price}</span>'
        
        products_html += f'''
        <div class="product-card bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow group">
            <div class="relative">
                {image_html}
                {flash_sale_badge}
                <button onclick="addToCart('{product.id}')" class="absolute bottom-2 right-2 bg-amber-700 hover:bg-amber-800 text-white p-2 sm:p-3 rounded-full shadow-lg transition-colors z-10 opacity-100 visible touch-manipulation">
                    <i class="fas fa-shopping-cart text-sm sm:text-base"></i>
                </button>
            </div>
            <div class="p-4">
                <a href="/product/{product.slug}/" class="block">
                    <h3 class="font-semibold mb-2 hover:text-amber-700 transition-colors line-clamp-2">{product.title}</h3>
                    {category_html}
                    <div class="flex items-center justify-between mb-3">
                        <div>
                            {price_html}
                        </div>
                    </div>
                </a>
            </div>
        </div>
        '''
    
    return products_html

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
        
        rating = int(request.POST.get('rating'))
        comment = request.POST.get('comment', '').strip()
        
        if not (1 <= rating <= 5):
            return JsonResponse({'success': False, 'error': 'Invalid rating'})
        
        if not comment:
            return JsonResponse({'success': False, 'error': 'Comment is required'})
        
        # Check if user already reviewed this product
        existing_review = ProductReview.objects.filter(
            product=product, 
            user=request.user
        ).first()
        
        if existing_review:
            return JsonResponse({'success': False, 'error': 'You have already reviewed this product'})
        
        # Create review
        review = ProductReview.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            comment=comment,
            is_approved=True  # Auto-approve for now
        )
        
        return JsonResponse({
            'success': True,
            'review': {
                'id': review.id,
                'rating': review.rating,
                'comment': review.comment,
                'user_name': review.user.get_full_name() or review.user.email,
                'created_at': review.created_at.strftime('%B %d, %Y'),
            }
        })
        
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
def load_more_reviews(request, product_id):
    """AJAX endpoint to load more reviews for a product.
    Accepts query param `offset` (int), returns next batch of reviews as JSON.
    """
    product = get_object_or_404(Product, id=product_id, is_active=True)
    try:
        offset = int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    limit = 10

    approved_reviews_qs = product.reviews.filter(is_approved=True).select_related('user')
    reviews = approved_reviews_qs[offset:offset + limit]

    reviews_data = []
    for review in reviews:
        reviews_data.append({
            'id': str(review.id),
            'rating': review.rating,
            'title': getattr(review, 'title', '') or '',
            'comment': review.comment,
            'user_email': getattr(review.user, 'email', ''),
            'created_at': review.created_at.strftime('%B %d, %Y') if getattr(review, 'created_at', None) else '',
            'is_verified_purchase': getattr(review, 'is_verified_purchase', False),
        })

    return JsonResponse({
        'reviews': reviews_data,
        'has_more': approved_reviews_qs.count() > offset + limit,
    })


def quick_view(request, product_id):
    """AJAX endpoint for quick product view"""
    try:
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        image_url = None
        if product.images.exists():
            image_url = product.images.first().image.url
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': str(product.id),
                'title': product.title,
                'slug': product.slug,
                'price': str(product.price),
                'sale_price': str(product.sale_price) if product.sale_price else None,
                'display_price': str(product.get_display_price()),
                'image_url': image_url,
                'description': product.description,
                'category': product.category.name if product.category else '',
                'has_flash_sale': product.has_active_flash_sale(),
                'flash_sale_end_time': product.flash_sale_end_time.isoformat() if product.flash_sale_end_time else None,
                'savings_percentage': product.get_savings_percentage(),
                'is_in_stock': product.is_in_stock(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def help_center(request):
    return render(request, 'store/customer_service/help_center.html')


def shipping_info(request):
    return render(request, 'store/customer_service/shipping_info.html')


def returns_refunds(request):
    return render(request, 'store/customer_service/returns_refunds.html')


def size_guide(request):
    return render(request, 'store/customer_service/size_guide.html')


def track_order(request):
    return render(request, 'store/customer_service/track_order.html')


def contact(request):
    return render(request, 'store/contact.html')


def about(request):
    return render(request, 'store/about.html')