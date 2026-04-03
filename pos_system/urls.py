from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include

urlpatterns = [
    path('', include('pos.urls')),
]

# runserver يضيف هذا تلقائياً؛ waitress وغيره من WSGI لا يضيفونه — بدونه /static/ يرجع 404
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
