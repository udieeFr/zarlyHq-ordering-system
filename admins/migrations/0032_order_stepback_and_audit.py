import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0031_digitalsignature_verify_token'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='step_back_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='order',
            name='stepped_back_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='stepped_back_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stepped_back_orders',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
