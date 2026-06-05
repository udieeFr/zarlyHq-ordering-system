"""
Management command: seed_orders
Creates 10 sample Malaysian customers and 50 sample orders across all statuses.
Assumes products already exist in the database.

Usage:
    python manage.py seed_orders
    python manage.py seed_orders --clear   # wipe seeded data first
"""
import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction

from customers.models import User, Product, CustomerProfile
from admins.models import Order, OrderItem, Payment


MALAYSIAN_NAMES = [
    ("Amirul", "Hakim", "amirul.hakim"),
    ("Nurul", "Aina", "nurul.aina"),
    ("Muhammad", "Faris", "muhammad.faris"),
    ("Siti", "Nabilah", "siti.nabilah"),
    ("Ahmad", "Zulkifli", "ahmad.zulkifli"),
    ("Nur", "Hidayah", "nur.hidayah"),
    ("Khairul", "Anuar", "khairul.anuar"),
    ("Farah", "Liyana", "farah.liyana"),
    ("Hafizuddin", "Razak", "hafizuddin.razak"),
    ("Zainab", "Othman", "zainab.othman"),
]

MALAYSIAN_ADDRESSES = [
    ("12, Jalan Bukit Bintang", "Kuala Lumpur", "Kuala Lumpur", "55100"),
    ("34-A, Jalan Ampang", "Kuala Lumpur", "Kuala Lumpur", "50450"),
    ("7, Lorong Maarof", "Bangsar", "Kuala Lumpur", "59000"),
    ("88, Jalan Ipoh", "Kepong", "Kuala Lumpur", "52200"),
    ("22, Jalan Cheras", "Cheras", "Selangor", "43200"),
    ("15, Jalan SS2/75", "Petaling Jaya", "Selangor", "47300"),
    ("3, Jalan Utama", "Georgetown", "Pulau Pinang", "10400"),
    ("101, Jalan Tun Abdul Razak", "Johor Bahru", "Johor", "80000"),
    ("45, Jalan Bendahara", "Seremban", "Negeri Sembilan", "70000"),
    ("9, Jalan Maharajalela", "Ipoh", "Perak", "30000"),
]

ORDER_NOTES_POOL = [
    "Tolong hantar sebelum pukul 12 tengah hari.",
    "Sila hubungi saya apabila tiba.",
    "Tinggalkan di pintu depan kalau tiada orang.",
    "Tiada nota khas.",
    "Extra sos cili kalau ada.",
    "Jangan ketuk pintu, ada bayi tidur.",
    "Hantar ke unit belakang.",
    None,
    None,
    None,
]

# Realistic spread: weight per status
STATUS_POOL = (
    ["pending"] * 16
    + ["approved"] * 8
    + ["prepared"] * 5
    + ["ready_for_delivery"] * 5
    + ["out_for_delivery"] * 5
    + ["delivered"] * 7
    + ["rejected"] * 2
    + ["cancelled"] * 2
)

PAYMENT_METHODS = ["stripe", "manual", "cash"]
COURIER_NAMES = ["J&T Express", "Pos Laju", "Ninja Van", "DHL eCommerce", "Lalamove"]


class Command(BaseCommand):
    help = "Seed 10 sample customers and 50 sample orders for UAT testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously seeded customers and their orders before seeding.",
        )

    def handle(self, *args, **options):
        products = list(Product.objects.filter(is_available=True))
        if not products:
            raise CommandError(
                "No available products found. Please add products before running this command."
            )

        if options["clear"]:
            deleted, _ = User.objects.filter(
                username__in=[row[2] for row in MALAYSIAN_NAMES]
            ).delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} seeded user(s) and their related data."))

        with transaction.atomic():
            customers = self._create_customers()
            orders = self._create_orders(customers, products)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {len(customers)} customers and {len(orders)} orders."
        ))

    def _create_customers(self):
        customers = []
        for first, last, username in MALAYSIAN_NAMES:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@zarlytest.my",
                    "role": "customer",
                    "email_verified": True,
                    "phone_number": f"+601{random.randint(1,9)}{random.randint(1000000,9999999)}",
                },
            )
            if created:
                user.set_password("TestPass123!")
                user.save()

            CustomerProfile.objects.get_or_create(user=user)
            customers.append(user)
            action = "Created" if created else "Found"
            self.stdout.write(f"  {action} customer: {user.username}")

        return customers

    def _create_orders(self, customers, products):
        statuses = STATUS_POOL[:]
        random.shuffle(statuses)
        orders = []
        now = timezone.now()

        for i in range(50):
            customer = random.choice(customers)
            address = random.choice(MALAYSIAN_ADDRESSES)
            status = statuses[i]
            created_offset = timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
            created_at = now - created_offset

            # Pick 1–3 products for this order
            chosen = random.sample(products, min(random.randint(1, 3), len(products)))
            items_data = []
            subtotal = Decimal("0.00")
            for product in chosen:
                qty = random.randint(1, 3)
                price = product.price
                items_data.append((product, qty, price))
                subtotal += price * qty

            shipping_fee = Decimal("8.00") if subtotal < Decimal("100.00") else Decimal("0.00")
            total = subtotal + shipping_fee

            order = Order(
                customer=customer,
                full_name=f"{customer.first_name} {customer.last_name}",
                phone_number=customer.phone_number,
                street_address=address[0],
                city=address[1],
                state=address[2],
                postcode=address[3],
                order_notes=random.choice(ORDER_NOTES_POOL),
                total_amount=total,
                shipping_fee=shipping_fee,
                status=status,
            )
            order.save()

            # Backdate created_at (auto_now_add prevents direct assignment)
            Order.objects.filter(pk=order.pk).update(created_at=created_at)
            order.refresh_from_db()

            for product, qty, price in items_data:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=price,
                    subtotal=price * qty,
                )

            self._attach_payment(order, total, status, created_at)
            self._set_status_timestamps(order, status, created_at)

            orders.append(order)

        self.stdout.write(f"  Created 50 orders across statuses.")
        return orders

    def _attach_payment(self, order, total, status, created_at):
        if status in ("cancelled", "rejected"):
            return

        method = random.choice(PAYMENT_METHODS)
        pay_status = "succeeded" if status in ("approved", "prepared", "ready_for_delivery", "out_for_delivery", "delivered") else "pending"

        if method == "cash":
            pay_status = "pending"

        Payment.objects.create(
            order=order,
            payment_method=method,
            status=pay_status,
            amount=total,
            currency="MYR",
            paid_at=created_at + timedelta(minutes=random.randint(5, 60)) if pay_status == "succeeded" else None,
        )

    def _set_status_timestamps(self, order, status, created_at):
        STATUS_ORDER = [
            "pending", "approved", "prepared",
            "ready_for_delivery", "out_for_delivery", "delivered",
        ]
        if status not in STATUS_ORDER:
            return

        idx = STATUS_ORDER.index(status)
        updates = {}
        t = created_at

        if idx >= 1:
            t += timedelta(hours=random.randint(1, 4))
            updates["approved_at"] = t
        if idx >= 2:
            t += timedelta(hours=random.randint(1, 3))
            updates["prepared_at"] = t
        if idx >= 3:
            t += timedelta(hours=random.randint(1, 2))
            updates["ready_for_delivery_at"] = t
        if idx >= 4:
            t += timedelta(hours=random.randint(1, 3))
            updates["delivery_assigned_at"] = t
            updates["courier_name"] = random.choice(COURIER_NAMES)
            updates["tracking_number"] = f"MY{random.randint(100000000, 999999999)}"
        if idx >= 5:
            t += timedelta(hours=random.randint(1, 5))
            updates["delivered_at"] = t

        if updates:
            Order.objects.filter(pk=order.pk).update(**updates)
