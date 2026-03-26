from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('order/new/', views.new_order, name='new_order'),
    path('order/preview/', views.preview_order, name='preview_order'),
    path('order/create/', views.create_order, name='create_order'),
    path('orders/', views.orders_list, name='orders_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/pay/', views.mark_paid, name='mark_paid'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('orders/<int:order_id>/reprint/', views.reprint_order, name='reprint_order'),
    path('reports/', views.reports, name='reports'),
    path('drawer/', views.open_drawer, name='open_drawer'),
]