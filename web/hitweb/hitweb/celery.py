import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hitweb.settings")
app = Celery("hitweb")
app.config_from_object("django.conf:settings", namespace="HITWEB")
app.autodiscover_tasks()


