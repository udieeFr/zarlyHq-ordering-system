from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0016_product_unlimited_stock'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='bundle_stock',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
