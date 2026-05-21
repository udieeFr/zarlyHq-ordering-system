from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0015_product_bundle_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_unlimited_stock',
            field=models.BooleanField(default=False),
        ),
    ]
