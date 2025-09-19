from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('store.urls')),
    path('orders/', include('orders.urls')),
    path('sell-items/', include('sell_items.urls')), 
    path('payments/', include('payments.urls')),
    path('blog/', include('blog.urls')),
    path('c/', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]

admin.site.site_header = "Success Direct Marketstore Admin"
admin.site.site_title = "Success Direct MarketStore Admin Portal"
admin.site.index_title = "Welcome to Success Direct Marketstore Administration"