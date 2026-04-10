# Generated manually — عدة طاولات لكل طلب

from django.db import migrations, models
import django.db.models.deletion


def forwards_copy_table_fk(apps, schema_editor):
    Order = apps.get_model('pos', 'Order')
    OrderTable = apps.get_model('pos', 'OrderTable')
    for o in Order.objects.filter(order_type='dine_in').exclude(table_id=None).iterator():
        OrderTable.objects.get_or_create(
            order_id=o.pk,
            table_id=o.table_id,
            defaults={'sort_order': 0},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0008_deliverycustomer'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderTable',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='الترتيب')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='table_links', to='pos.order', verbose_name='الطلب')),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='order_links', to='pos.table', verbose_name='الطاولة')),
            ],
            options={
                'verbose_name': 'طاولة ضمن طلب',
                'verbose_name_plural': 'طاولات الطلب',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='ordertable',
            constraint=models.UniqueConstraint(fields=('order', 'table'), name='uniq_pos_ordertable_order_table'),
        ),
        migrations.RunPython(forwards_copy_table_fk, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='order',
            name='table',
        ),
    ]
