from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0029_auditlog_action_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='internal_note',
            field=models.TextField(blank=True, default=''),
        ),
    ]
