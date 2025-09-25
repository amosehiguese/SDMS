from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from store.models import Product

def search_products(request):
    """AJAX search for products"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'products': []})
    
    products = Product.objects.filter(
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(category__name__icontains=query)
    ).select_related('category').prefetch_related('images')[:20]
    
    products_data = []
    for product in products:
        image_url = None
        if product.images.exists():
            image_url = product.images.first().image.url
        
        products_data.append({
            'id': str(product.id),
            'title': product.title,
            'slug': product.slug,
            'price': str(product.get_display_price()),
            'image_url': image_url,
            'category': product.category.name if product.category else '',
            'has_flash_sale': product.has_active_flash_sale(),
        })
    
    return JsonResponse({'products': products_data})


@login_required
def profile_view(request):
    """User profile view"""
    return render(request, 'account/profile.html')
