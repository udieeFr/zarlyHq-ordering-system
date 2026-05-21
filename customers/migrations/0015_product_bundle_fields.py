from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0014_backfill_email_verified'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='bundle_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='bundle_quantity',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='bundle_weight_grams',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
