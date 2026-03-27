from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0002_printed_status'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Drop old tables
        migrations.DeleteModel(name='OrderItem'),
        migrations.DeleteModel(name='Order'),
        migrations.DeleteModel(name='Table'),
        migrations.DeleteModel(name='MenuItem'),
        migrations.DeleteModel(name='Category'),

        # Re-create Category
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100, verbose_name='الاسم')),
                ('category_type', models.CharField(
                    choices=[('food','أكل'),('drink','مشروبات'),('other','أخرى')],
                    default='other', max_length=10, verbose_name='النوع')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='الترتيب')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
            ],
            options={'verbose_name':'تصنيف','verbose_name_plural':'التصنيفات','ordering':['order','name']},
        ),
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=200, verbose_name='الاسم')),
                ('price', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='السعر')),
                ('is_available', models.BooleanField(default=True, verbose_name='متاح')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='الترتيب')),
                ('description', models.TextField(blank=True, verbose_name='الوصف')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pos.category', verbose_name='التصنيف')),
            ],
            options={'verbose_name':'منتج','verbose_name_plural':'المنتجات','ordering':['order','name']},
        ),
        migrations.CreateModel(
            name='Waiter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100, verbose_name='الاسم')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='الهاتف')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
            ],
            options={'verbose_name':'ويتر','verbose_name_plural':'الويترين','ordering':['name']},
        ),
        migrations.CreateModel(
            name='DeliveryDriver',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100, verbose_name='الاسم')),
                ('phone', models.CharField(max_length=20, verbose_name='رقم الهاتف')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
            ],
            options={'verbose_name':'طيار ديليفري','verbose_name_plural':'طياري الديليفري','ordering':['name']},
        ),
        migrations.CreateModel(
            name='Table',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('number', models.PositiveIntegerField(unique=True, verbose_name='رقم الطاولة')),
                ('name', models.CharField(blank=True, max_length=50, verbose_name='الاسم')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشطة')),
            ],
            options={'verbose_name':'طاولة','verbose_name_plural':'الطاولات','ordering':['number']},
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('order_type', models.CharField(choices=[('dine_in','داخل المحل'),('delivery','ديليفري')], default='dine_in', max_length=20, verbose_name='نوع الطلب')),
                ('status', models.CharField(choices=[('open','مفتوح'),('printed','قيد الانتظار'),('completed','مكتمل'),('cancelled','ملغي')], default='open', max_length=20, verbose_name='الحالة')),
                ('notes', models.TextField(blank=True, verbose_name='ملاحظات')),
                ('customer_name', models.CharField(blank=True, max_length=150, verbose_name='اسم العميل')),
                ('customer_phone', models.CharField(blank=True, max_length=30, verbose_name='رقم العميل')),
                ('customer_address', models.TextField(blank=True, verbose_name='عنوان العميل')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('printed_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cashier', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='auth.user', verbose_name='الكاشير')),
                ('table', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.table', verbose_name='الطاولة')),
                ('waiter', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.waiter', verbose_name='الويتر')),
                ('driver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.deliverydriver', verbose_name='الطيار')),
                ('cancel_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_cancels', to='auth.user')),
            ],
            options={'verbose_name':'طلب','verbose_name_plural':'الطلبات','ordering':['-created_at']},
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='الكمية')),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='السعر')),
                ('notes', models.CharField(blank=True, max_length=200, verbose_name='ملاحظات')),
                ('menu_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pos.menuitem', verbose_name='المنتج')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pos.order', verbose_name='الطلب')),
            ],
            options={'verbose_name':'عنصر طلب','verbose_name_plural':'عناصر الطلب'},
        ),
        migrations.CreateModel(
            name='InventoryEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=200, verbose_name='اسم الصنف')),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='الكمية')),
                ('unit', models.CharField(blank=True, max_length=50, verbose_name='الوحدة')),
                ('total_cost', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='التكلفة الإجمالية')),
                ('date', models.DateField(default=django.utils.timezone.now, verbose_name='تاريخ الوارد')),
                ('notes', models.TextField(blank=True, verbose_name='ملاحظات')),
                ('added_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='أضافه')),
            ],
            options={'verbose_name':'وارد مخزون','verbose_name_plural':'واردات المخزون','ordering':['-date','-id']},
        ),
        migrations.CreateModel(
            name='Shift',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('start_time', models.DateTimeField(auto_now_add=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('open','مفتوح'),('closed','مغلق')], default='open', max_length=10)),
                ('cash_in_drawer', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='الفلوس في الدرج')),
                ('system_total', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='إجمالي السيستم')),
                ('difference', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='الفرق')),
                ('notes', models.TextField(blank=True)),
                ('cashier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shifts', to='auth.user', verbose_name='الكاشير')),
            ],
            options={'verbose_name':'شيفت','verbose_name_plural':'الشيفتات','ordering':['-start_time']},
        ),
        migrations.CreateModel(
            name='CashierProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('can_view_totals', models.BooleanField(default=False, verbose_name='يشوف الإجماليات')),
                ('can_view_history', models.BooleanField(default=False, verbose_name='يشوف التاريخ بدون إذن')),
                ('can_open_drawer', models.BooleanField(default=False, verbose_name='يفتح الدرج بدون إذن')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='الهاتف')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='cashier_profile', to='auth.user')),
            ],
            options={'verbose_name':'بروفايل كاشير','verbose_name_plural':'بروفايلات الكاشير'},
        ),
    ]
