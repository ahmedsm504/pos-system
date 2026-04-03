from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Category(models.Model):
    TYPE_CHOICES = [('food','أكل'),('drink','مشروبات'),('other','أخرى')]
    name          = models.CharField(max_length=100, verbose_name='الاسم')
    category_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='other', verbose_name='النوع')
    order         = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    is_active     = models.BooleanField(default=True, verbose_name='نشط')
    enable_sizes = models.BooleanField(
        default=False, verbose_name='أحجام للأصناف',
        help_text='عند التفعيل يُعرّف لكل صنف أسعار لعدة أحجام بدل سعر واحد فقط.',
    )
    enable_addons = models.BooleanField(
        default=False, verbose_name='إضافات اختيارية',
        help_text='قائمة إضافات بأسعار (مثل جبن، بطاطس) تُزاد على سعر الصنف عند الطلب.',
    )
    enable_drink_options = models.BooleanField(
        default=False, verbose_name='خيارات تفصيل المشروب',
        help_text='عناوين جاهزة (بدون سكر، زيادة ثلج…) + نص حر؛ تظهر في الفاتورة والمطبخ والبار.',
    )
    class Meta:
        verbose_name='تصنيف'; verbose_name_plural='التصنيفات'; ordering=['order','name']
    def __str__(self): return self.name


class CategoryAddon(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='addons', verbose_name='التصنيف')
    name = models.CharField(max_length=120, verbose_name='الاسم')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='السعر')
    order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    class Meta:
        verbose_name='إضافة تصنيف'; verbose_name_plural='إضافات التصنيف'; ordering=['order', 'id']
    def __str__(self): return f'{self.name} (+{self.price})'


class DrinkOptionPreset(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='drink_presets', verbose_name='التصنيف')
    label = models.CharField(max_length=120, verbose_name='النص')
    order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    class Meta:
        verbose_name='خيار مشروب'; verbose_name_plural='خيارات المشروبات'; ordering=['order', 'id']
    def __str__(self): return self.label


class MenuItem(models.Model):
    category     = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items', verbose_name='التصنيف')
    name         = models.CharField(max_length=200, verbose_name='الاسم')
    price        = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='السعر الأساسي')
    is_available = models.BooleanField(default=True, verbose_name='متاح')
    order        = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    description  = models.TextField(blank=True, verbose_name='الوصف')
    class Meta:
        verbose_name='منتج'; verbose_name_plural='المنتجات'; ordering=['order','name']
    def __str__(self): return f"{self.name} — {self.price} ج"

    def menu_grid_price(self):
        """أقل سعر حجم أو السعر الأساسي (للعرض في بطاقة المنيو)."""
        try:
            sz = list(self.sizes.all())
            if sz:
                return min(s.price for s in sz)
        except Exception:
            pass
        return self.price


class MenuItemSize(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='sizes', verbose_name='الصنف')
    name = models.CharField(max_length=80, verbose_name='اسم الحجم')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='السعر')
    order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    class Meta:
        verbose_name='حجم صنف'; verbose_name_plural='أحجام الأصناف'; ordering=['order', 'id']
    def __str__(self): return f'{self.menu_item.name} — {self.name}'


class Waiter(models.Model):
    name      = models.CharField(max_length=100, verbose_name='الاسم')
    phone     = models.CharField(max_length=20, blank=True, verbose_name='الهاتف')
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    class Meta:
        verbose_name='ويتر'; verbose_name_plural='الويترين'; ordering=['name']
    def __str__(self): return self.name


class DeliveryDriver(models.Model):
    name      = models.CharField(max_length=100, verbose_name='الاسم')
    phone     = models.CharField(max_length=20, verbose_name='رقم الهاتف')
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    class Meta:
        verbose_name='طيار ديليفري'; verbose_name_plural='طياري الديليفري'; ordering=['name']
    def __str__(self): return f"{self.name} ({self.phone})"


class Table(models.Model):
    number    = models.PositiveIntegerField(unique=True, verbose_name='رقم الطاولة')
    name      = models.CharField(max_length=50, blank=True, verbose_name='الاسم')
    is_active = models.BooleanField(default=True, verbose_name='نشطة')
    class Meta:
        verbose_name='طاولة'; verbose_name_plural='الطاولات'; ordering=['number']
    def __str__(self):
        return f"طاولة {self.number}" + (f" — {self.name}" if self.name else "")


class Order(models.Model):
    STATUS_CHOICES = [
        ('open','مفتوح'),
        ('printed','قيد الانتظار'),
        ('completed','مكتمل'),
        ('cancelled','ملغي'),
    ]
    TYPE_CHOICES = [('dine_in','داخل المحل'),('delivery','ديليفري')]

    cashier          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='orders', verbose_name='الكاشير')
    order_type       = models.CharField(max_length=20, choices=TYPE_CHOICES, default='dine_in', verbose_name='نوع الطلب')
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name='الحالة')
    notes            = models.TextField(blank=True, verbose_name='ملاحظات')
    table            = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الطاولة')
    waiter           = models.ForeignKey(Waiter, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الويتر')
    customer_name    = models.CharField(max_length=150, blank=True, verbose_name='اسم العميل')
    customer_phone   = models.CharField(max_length=30, blank=True, verbose_name='رقم العميل')
    customer_address = models.TextField(blank=True, verbose_name='عنوان العميل')
    driver           = models.ForeignKey(DeliveryDriver, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الطيار')
    created_at       = models.DateTimeField(auto_now_add=True)
    printed_at       = models.DateTimeField(null=True, blank=True)
    completed_at     = models.DateTimeField(null=True, blank=True)
    cancelled_at     = models.DateTimeField(null=True, blank=True)
    cancel_approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_cancels')

    class Meta:
        verbose_name='طلب'; verbose_name_plural='الطلبات'; ordering=['-created_at']

    def __str__(self): return f"طلب #{self.id}"

    @property
    def total(self):
        return sum(i.subtotal for i in self.items.all())

    @property
    def total_items(self):
        return sum(i.quantity for i in self.items.all())


class OrderItem(models.Model):
    order     = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='الطلب')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name='المنتج')
    quantity  = models.PositiveIntegerField(default=1, verbose_name='الكمية')
    price     = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='سعر الوحدة')
    notes     = models.CharField(max_length=200, blank=True, verbose_name='ملاحظات')
    selected_size = models.ForeignKey(
        'MenuItemSize', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_lines', verbose_name='الحجم',
    )
    size_label = models.CharField(max_length=100, blank=True, verbose_name='اسم الحجم (نسخة)')
    drink_detail = models.TextField(blank=True, verbose_name='تفاصيل المشروب')
    extras_json = models.JSONField(default=dict, blank=True, verbose_name='إضافات وخيارات (JSON)')
    class Meta:
        verbose_name='عنصر طلب'; verbose_name_plural='عناصر الطلب'
    def __str__(self): return f"{self.quantity}× {self.menu_item.name}"
    @property
    def subtotal(self): return self.quantity * (self.price or 0)
    def save(self, *args, **kwargs):
        if self.price is None:
            if self.selected_size_id:
                self.price = self.selected_size.price
            else:
                self.price = self.menu_item.price
        super().save(*args, **kwargs)


class InventoryEntry(models.Model):
    name       = models.CharField(max_length=200, verbose_name='اسم الصنف')
    quantity   = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية')
    unit       = models.CharField(max_length=50, blank=True, verbose_name='الوحدة')
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='التكلفة الإجمالية')
    date       = models.DateField(default=timezone.now, verbose_name='تاريخ الوارد')
    added_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='أضافه')
    notes      = models.TextField(blank=True, verbose_name='ملاحظات')
    # وارد من شيفت كاشير (بعد موافقة المدير) — يُخصم من المتوقع في الدرج عند إغلاق الشيفت
    shift = models.ForeignKey(
        'Shift', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_entries', verbose_name='الشيفت',
    )
    recorded_by_cashier = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cashier_inventory_entries', verbose_name='الكاشير (التسجيل)',
    )
    class Meta:
        verbose_name='وارد مخزون'; verbose_name_plural='واردات المخزون'; ordering=['-date','-id']
    def __str__(self): return f"{self.name} — {self.total_cost} ج"


class Shift(models.Model):
    cashier        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shifts', verbose_name='الكاشير')
    start_time     = models.DateTimeField(auto_now_add=True)
    end_time       = models.DateTimeField(null=True, blank=True)
    status         = models.CharField(max_length=10, choices=[('open','مفتوح'),('closed','مغلق')], default='open')
    cash_in_drawer = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='الدرج بعد العدّ',
        help_text='ما أدخله الكاشير عند إغلاق الشيفت بعد عدّ النقد.',
    )
    system_total   = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='مجموع المطابقة',
        help_text='مفروض المبيعات (طلبات) + واردات الشيفت؛ يُقارن بالدرج لحساب الزيادة أو العجز.',
    )
    difference     = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='الفرق (الدرج − المطابقة)',
        help_text='موجب = زيادة في الدرج، سالب = عجز عن المطابقة.',
    )
    notes          = models.TextField(blank=True)
    class Meta:
        verbose_name='شيفت'; verbose_name_plural='الشيفتات'; ordering=['-start_time']
    def __str__(self): return f"شيفت {self.cashier.username}"


class CashierProfile(models.Model):
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cashier_profile')
    can_view_totals  = models.BooleanField(default=False, verbose_name='يشوف الإجماليات')
    can_view_history = models.BooleanField(default=False, verbose_name='يشوف التاريخ بدون إذن')
    can_open_drawer  = models.BooleanField(default=False, verbose_name='يفتح الدرج بدون إذن')
    phone            = models.CharField(max_length=20, blank=True, verbose_name='الهاتف')
    class Meta:
        verbose_name='بروفايل كاشير'; verbose_name_plural='بروفايلات الكاشير'
    def __str__(self): return f"بروفايل — {self.user.username}"
