from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='printed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='وقت الطباعة'),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('open', 'مفتوح'),
                    ('printed', 'مطبوع'),
                    ('paid', 'مدفوع'),
                    ('cancelled', 'ملغي'),
                ],
                default='open',
                max_length=20,
                verbose_name='الحالة',
            ),
        ),
    ]
