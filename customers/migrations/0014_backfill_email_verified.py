from django.db import migrations


def backfill_email_verified(apps, schema_editor):
    """All accounts that existed before this feature ships are considered verified."""
    User = apps.get_model('customers', 'User')
    User.objects.all().update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0013_user_email_verified'),
    ]

    operations = [
        migrations.RunPython(backfill_email_verified, migrations.RunPython.noop),
    ]
