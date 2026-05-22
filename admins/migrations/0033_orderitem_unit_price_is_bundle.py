from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0032_order_stepback_and_audit'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='orderitem',
            name='is_bundle',
            field=models.BooleanField(default=False),
        ),
    ]
