from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='الاسم')),
                ('category_type', models.CharField(
                    choices=[('food', 'أكل'), ('drink', 'مشروبات'), ('other', 'أخرى')],
                    default='other', max_length=10, verbose_name='النوع'
                )),
                ('order', models.PositiveIntegerField(default=0, verbose_name='الترتيب')),
            ],
            options={'verbose_name': 'تصنيف', 'verbose_name_plural': 'التصنيفات', 'ordering': ['order', 'name']},
        ),
        migrations.CreateModel(
            name='Table',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField(unique=True, verbose_name='رقم الطاولة')),
                ('name', models.CharField(blank=True, max_length=50, verbose_name='الاسم (اختياري)')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشطة')),
            ],
            options={'verbose_name': 'طاولة', 'verbose_name_plural': 'الطاولات', 'ordering': ['number']},
        ),
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='الاسم')),
                ('price', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='السعر')),
                ('is_available', models.BooleanField(default=True, verbose_name='متاح')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='الترتيب')),
                ('category', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='pos.category', verbose_name='التصنيف'
                )),
            ],
            options={'verbose_name': 'منتج', 'verbose_name_plural': 'المنتجات', 'ordering': ['order', 'name']},
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('open', 'مفتوح'), ('paid', 'مدفوع'), ('cancelled', 'ملغي')],
                    default='open', max_length=20, verbose_name='الحالة'
                )),
                ('notes', models.TextField(blank=True, verbose_name='ملاحظات')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='وقت الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')),
                ('paid_at', models.DateTimeField(blank=True, null=True, verbose_name='وقت الدفع')),
                ('cashier', models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to='auth.user', verbose_name='الكاشير'
                )),
                ('table', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to='pos.table', verbose_name='الطاولة'
                )),
            ],
            options={'verbose_name': 'طلب', 'verbose_name_plural': 'الطلبات', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='الكمية')),
                ('price', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=8,
                    null=True, verbose_name='السعر وقت الطلب'
                )),
                ('notes', models.CharField(blank=True, max_length=200, verbose_name='ملاحظات')),
                ('menu_item', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='pos.menuitem', verbose_name='المنتج'
                )),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items', to='pos.order', verbose_name='الطلب'
                )),
            ],
            options={'verbose_name': 'عنصر طلب', 'verbose_name_plural': 'عناصر الطلب'},
        ),
    ]
