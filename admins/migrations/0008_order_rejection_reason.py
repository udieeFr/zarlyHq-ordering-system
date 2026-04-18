from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0007_order_geolocation'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='rejection_reason',
            field=models.TextField(blank=True, null=True),
        ),
    ]
