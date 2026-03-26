from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name='الاسم')
    category_type = models.CharField(
        max_length=10,
        choices=[('food', 'أكل'), ('drink', 'مشروبات'), ('other', 'أخرى')],
        default='other',
        verbose_name='النوع'
    )
    order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')

    class Meta:
        verbose_name = 'تصنيف'
        verbose_name_plural = 'التصنيفات'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items', verbose_name='التصنيف')
    name = models.CharField(max_length=200, verbose_name='الاسم')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='السعر')
    is_available = models.BooleanField(default=True, verbose_name='متاح')
    order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')

    class Meta:
        verbose_name = 'منتج'
        verbose_name_plural = 'المنتجات'
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} - {self.price} ج"


class Table(models.Model):
    number = models.PositiveIntegerField(unique=True, verbose_name='رقم الطاولة')
    name = models.CharField(max_length=50, blank=True, verbose_name='الاسم (اختياري)')
    is_active = models.BooleanField(default=True, verbose_name='نشطة')

    class Meta:
        verbose_name = 'طاولة'
        verbose_name_plural = 'الطاولات'
        ordering = ['number']

    def __str__(self):
        return f"طاولة {self.number}" + (f" - {self.name}" if self.name else "")


class Order(models.Model):
    STATUS_CHOICES = [
        ('open', 'مفتوح'),
        ('printed', 'مطبوع'),
        ('paid', 'مدفوع'),
        ('cancelled', 'ملغي'),
    ]

    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الطاولة')
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='الكاشير')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name='الحالة')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')
    printed_at = models.DateTimeField(null=True, blank=True, verbose_name='وقت الطباعة')
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name='وقت الدفع')

    class Meta:
        verbose_name = 'طلب'
        verbose_name_plural = 'الطلبات'
        ordering = ['-created_at']

    def __str__(self):
        return f"طلب #{self.id} - {self.get_status_display()}"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='الطلب')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name='المنتج')
    quantity = models.PositiveIntegerField(default=1, verbose_name='الكمية')
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='السعر وقت الطلب')
    notes = models.CharField(max_length=200, blank=True, verbose_name='ملاحظات')

    class Meta:
        verbose_name = 'عنصر طلب'
        verbose_name_plural = 'عناصر الطلب'

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name}"

    @property
    def subtotal(self):
        return self.quantity * self.price

    def save(self, *args, **kwargs):
        # Save current price at time of order
        if self.price is None:
            self.price = self.menu_item.price
        super().save(*args, **kwargs)
