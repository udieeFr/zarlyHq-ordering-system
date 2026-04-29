from django.db import models
from django.utils import timezone
from customers.models import User, Product

class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('prepared', 'Prepared'),
        ('ready_for_delivery', 'Ready for Delivery'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('rejected', 'Rejected'),
        ('pending_payment', 'Approved but pending payment'),
    )
    
    customer = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'customer'})
    full_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    street_address = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=120, null=True, blank=True)
    state = models.CharField(max_length=120, null=True, blank=True)
    postcode = models.CharField(max_length=20, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    formatted_address = models.TextField(blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    order_notes = models.TextField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    payment_proof = models.ImageField(upload_to='payment_proofs/', null=True, blank=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_orders', limit_choices_to={'role__in': ['sales_admin', 'manager']})
    prepared_at = models.DateTimeField(null=True, blank=True)
    prepared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='prepared_orders', limit_choices_to={'role__in': ['sales_admin', 'manager']})
    ready_for_delivery_at = models.DateTimeField(null=True, blank=True)
    ready_for_delivery_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                              related_name='ready_for_delivery_orders', limit_choices_to={'role__in': ['sales_admin', 'manager']})
    courier_name = models.CharField(max_length=50, null=True, blank=True)
    tracking_number = models.CharField(max_length=100, null=True, blank=True)
    delivery_assigned_at = models.DateTimeField(null=True, blank=True)
    delivery_assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='delivery_assigned_orders', limit_choices_to={'role__in': ['sales_admin', 'manager']})
    delivered_at = models.DateTimeField(null=True, blank=True)

    @property
    def address_summary(self):
        if self.formatted_address:
            return self.formatted_address
        parts = [self.street_address, self.city, self.state, self.postcode]
        return ', '.join([part for part in parts if part])

    def __str__(self):
        return f"Order #{self.id} - {self.customer} ({self.status})"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.product.price * self.quantity
        super().save(*args, **kwargs)

class DigitalSignature(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='digital_signature')
    signature_hash = models.CharField(max_length=64)  
    pdf_path = models.FileField(upload_to='signed_pdfs/') 
    timestamp = models.DateTimeField(auto_now_add=True)
    signature_value = models.TextField()

class Payment(models.Model):
    """
    Tracks payment transactions (Stripe, manual proof, etc).
    One order can have multiple payment attempts (e.g., first fails, second succeeds).
    This keeps payment audit trail separate from order state.
    """
    PAYMENT_METHOD_CHOICES = (
        ('stripe', 'Stripe Card Payment'),
        ('manual', 'Manual Proof (Bank Transfer / DuitNow)'),
        ('cash', 'Cash on Delivery'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Payment Initiated'),
        ('processing', 'Payment Processing'),
        ('succeeded', 'Payment Succeeded'),
        ('failed', 'Payment Failed'),
        ('cancelled', 'Payment Cancelled'),
        ('refunded', 'Refunded'),
    )
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Amount paid
    currency = models.CharField(max_length=3, default='MYR')
    
    # Stripe-specific fields
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_charge_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    
    # Manual payment fields
    payment_reference = models.CharField(max_length=255, null=True, blank=True)  # Bank ref or transaction id
    proof_image = models.ImageField(upload_to='payment_proofs/', null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # For webhook audit trail
    last_webhook_event = models.CharField(max_length=100, null=True, blank=True)
    webhook_event_timestamp = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Payment #{self.id} - Order #{self.order.id} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['stripe_session_id']),
            models.Index(fields=['stripe_payment_intent_id']),
        ]

class Complaint(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('resolved', 'Resolved'),
    )
    # NEW: Specific outcomes for accountability
    ACTION_CHOICES = (
        ('refund', 'Contact User for Refund'),
        ('remake', 'Remake Order'),
        ('dismissed', 'Dismiss Complaint'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='complaints')
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    evidence_image = models.ImageField(upload_to='complaint_evidence/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # NEW: Field to store the admin's decision
    action_taken = models.CharField(max_length=50, choices=ACTION_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Complaint #{self.id} - Order #{self.order.id}"

class PrepGroup(models.Model):
    """Groups orders that were prepared together."""
    group_id = models.CharField(max_length=20, unique=True)
    orders = models.ManyToManyField(Order, related_name='prep_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_prep_groups', limit_choices_to={'role__in': ['sales_admin', 'manager']})
    total_orders = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if not self.group_id:
            self.group_id = f"GRP{timezone.now().strftime('%Y%m%d%H%M%S')}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Prep Group {self.group_id} - {self.total_orders} orders"

    @property
    def item_summary(self):
        """Aggregate items across all orders in this group."""
        item_counts = {}
        for order in self.orders.all():
            for item in order.items.all():
                key = item.product.name
                if key in item_counts:
                    item_counts[key]['quantity'] += item.quantity
                    item_counts[key]['orders'].append(order.id)
                else:
                    item_counts[key] = {
                        'quantity': item.quantity,
                        'price': item.product.price,
                        'subtotal': item.product.price * item.quantity,
                        'orders': [order.id]
                    }
        return sorted(item_counts.items(), key=lambda x: x[1]['quantity'], reverse=True)