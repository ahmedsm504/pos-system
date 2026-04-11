from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pos', '0010_order_shift_link'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderActivity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[
                        ('created', 'إنشاء الطلب'),
                        ('printed', 'طباعة وإرسال'),
                        ('item_added', 'إضافة صنف'),
                        ('item_modified', 'تعديل صنف'),
                        ('item_removed', 'حذف صنف'),
                        ('completed', 'إنهاء الطلب'),
                        ('cancelled', 'إلغاء الطلب'),
                        ('reprinted', 'إعادة طباعة'),
                        ('tables_changed', 'تعديل الطاولات'),
                        ('driver_changed', 'تعديل الطيار'),
                    ],
                    max_length=20,
                )),
                ('description', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='activities',
                    to='pos.order',
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'نشاط طلب',
                'verbose_name_plural': 'أنشطة الطلبات',
                'ordering': ['created_at'],
            },
        ),
    ]
