# Generated manually for MenuItemCashierPreset

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0012_alter_orderactivity_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='MenuItemCashierPreset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=120, verbose_name='نص يظهر للكاشير')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='الترتيب')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
                ('menu_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cashier_presets', to='pos.menuitem', verbose_name='الصنف')),
            ],
            options={
                'verbose_name': 'تعليق مساعد للصنف',
                'verbose_name_plural': 'تعليقات مساعدة للصنف',
                'ordering': ['order', 'id'],
            },
        ),
    ]
