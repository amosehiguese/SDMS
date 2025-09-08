import os
from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sdms.settings')

app = Celery('sdms')

app.config_from_object('django.conf:settings', namespace='CELERY')
 
app.autodiscover_tasks()

