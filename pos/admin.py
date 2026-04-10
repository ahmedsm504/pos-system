from django.contrib import admin
from .models import Category, MenuItem, Table, Order, OrderItem, DeliveryCustomer


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
    list_display = ['id', 'tables_label_display', 'cashier', 'status', 'total', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['created_at', 'completed_at']
    inlines = [OrderItemInline]

    @admin.display(description='الطاولة')
    def tables_label_display(self, obj):
        return obj.tables_label()


@admin.register(DeliveryCustomer)
class DeliveryCustomerAdmin(admin.ModelAdmin):
    list_display = ['phone_key', 'display_phone', 'name', 'updated_at']
    search_fields = ['phone_key', 'display_phone', 'name', 'address']
    readonly_fields = ['created_at', 'updated_at']