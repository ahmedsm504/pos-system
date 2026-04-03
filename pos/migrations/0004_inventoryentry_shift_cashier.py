from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pos', '0003_full_rebuild'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventoryentry',
            name='recorded_by_cashier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cashier_inventory_entries',
                to=settings.AUTH_USER_MODEL,
                verbose_name='الكاشير (التسجيل)',
            ),
        ),
        migrations.AddField(
            model_name='inventoryentry',
            name='shift',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='inventory_entries',
                to='pos.shift',
                verbose_name='الشيفت',
            ),
        ),
    ]
