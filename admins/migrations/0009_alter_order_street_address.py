from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0008_order_rejection_reason'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='street_address',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
