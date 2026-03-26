from django.contrib import admin
from .models import Category, MenuItem, Table, Order, OrderItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category_type', 'order']
    list_editable = ['order', 'category_type']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'order']
    list_editable = ['price', 'is_available', 'order']
    list_filter = ['category', 'is_available']


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'is_active']
    list_editable = ['name', 'is_active']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'table', 'cashier', 'status', 'total', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['created_at', 'updated_at', 'paid_at']
    inlines = [OrderItemInline]
