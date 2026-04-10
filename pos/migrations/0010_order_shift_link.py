from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0009_order_multi_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='shift',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='orders',
                to='pos.shift',
                verbose_name='الشيفت',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='shift_order_number',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name='رقم الطلب في الشيفت',
            ),
        ),
    ]
