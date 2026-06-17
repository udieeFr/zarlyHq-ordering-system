from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from admins.models import Order, OrderEvent

TIMEOUT_MINUTES = 30


class Command(BaseCommand):
    help = f'Cancel orders stuck in pending_confirmation for more than {TIMEOUT_MINUTES} minutes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            default='true',
            help='Set to false to actually cancel orders (default: true = preview only)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run'].lower() != 'false'
        cutoff = timezone.now() - timedelta(minutes=TIMEOUT_MINUTES)
        stale = Order.objects.filter(
            status='pending_confirmation',
            created_at__lt=cutoff,
        ).select_related('customer').prefetch_related('items__product')

        count = stale.count()
        if dry_run:
            self.stdout.write(f'[DRY RUN] Would cancel {count} unconfirmed order(s).')
            for order in stale:
                self.stdout.write(f'  Order #{order.id} — {order.customer.username} — created {order.created_at}')
            return

        cancelled = 0
        for order in stale:
            with transaction.atomic():
                for item in order.items.all():
                    if item.is_bundle:
                        if not item.product.is_unlimited_stock and item.product.bundle_stock is not None:
                            item.product.bundle_stock += item.quantity
                            item.product.save(update_fields=['bundle_stock'])
                    else:
                        if not item.product.is_unlimited_stock:
                            item.product.stock += item.quantity
                            item.product.save(update_fields=['stock'])
                order.status = 'cancelled'
                order.save(update_fields=['status'])
                OrderEvent.objects.create(
                    order=order, status='cancelled', actor=None,
                    note=f'Auto-cancelled: OTP confirmation timeout ({TIMEOUT_MINUTES} min)',
                )
            cancelled += 1

        self.stdout.write(self.style.SUCCESS(f'Cancelled {cancelled} unconfirmed order(s).'))
