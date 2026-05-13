from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='admins.Order')
def sync_customer_phone(sender, instance, created, **kwargs):
    """Keep CustomerProfile.default_phone in sync with the customer's most recent order phone."""
    if not instance.phone_number:
        return
    try:
        from customers.models import CustomerProfile
        profile, _ = CustomerProfile.objects.get_or_create(user=instance.customer)
        if profile.default_phone != instance.phone_number:
            profile.default_phone = instance.phone_number
            profile.save(update_fields=['default_phone', 'updated_at'])
    except Exception:
        pass
