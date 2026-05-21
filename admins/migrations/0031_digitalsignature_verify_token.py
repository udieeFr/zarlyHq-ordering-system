import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0030_order_internal_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='digitalsignature',
            name='verify_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
