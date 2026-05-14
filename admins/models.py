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
        ('cancelled', 'Cancelled by Customer'),
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

    # Walk-in / manually-created orders
    is_walk_in = models.BooleanField(default=False)

    # Remake / priority fields
    is_remake = models.BooleanField(default=False)
    remake_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='remakes')
    is_priority = models.BooleanField(default=False)

    @property
    def customer_label(self):
        """Display name for this order's customer — handles walk-in orders gracefully."""
        if self.is_walk_in:
            return f"Walk-in: {self.full_name or '—'}"
        return self.customer.username if self.customer_id else '—'

    @property
    def payment_proof(self):
        """Backwards-compat property — reads from the manual Payment record's proof_image."""
        payment = self.payments.filter(
            payment_method='manual',
            proof_image__isnull=False,
        ).exclude(proof_image='').order_by('-created_at').first()
        return payment.proof_image if payment else None

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
    signature_value = models.TextField(blank=True, default='')

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

    def save(self, *args, **kwargs):
        if not self.group_id:
            today = timezone.now().strftime('%y%m%d')
            prefix = f'OP-{today}-'
            last = (PrepGroup.objects
                    .filter(group_id__startswith=prefix)
                    .order_by('-group_id')
                    .first())
            seq = int(last.group_id.split('-')[-1]) + 1 if last else 1
            self.group_id = f'{prefix}{seq:02d}'
        super().save(*args, **kwargs)

    @property
    def total_orders(self):
        return getattr(self, '_total_orders', None) or self.orders.count()

    @property
    def total_amount(self):
        from django.db.models import Sum
        val = getattr(self, '_total_amount', None)
        if val is not None:
            return val
        result = self.orders.aggregate(s=Sum('total_amount'))['s']
        return result or 0

    def __str__(self):
        return f"Order Preparation {self.group_id} — {self.total_orders} orders"

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


class OrderEvent(models.Model):
    """
    Immutable log of every status transition on an order.
    Replaces the 9 nullable timestamp/actor columns on Order with a proper
    history table — one row per state change, queryable by date range or actor.
    """
    STATUS_CHOICES = Order.STATUS_CHOICES

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='events')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='order_events')
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['order', '-timestamp']),
        ]

    def __str__(self):
        who = self.actor.username if self.actor else 'system'
        return f"Order #{self.order_id} → {self.status} by {who} at {self.timestamp:%Y-%m-%d %H:%M}"


class RejectionReason(models.Model):
    """Predefined rejection reasons for dropdown selection."""
    CATEGORY_CHOICES = (
        ('system', 'System Error'),
        ('customer', 'Customer Issue'),
        ('payment', 'Payment Issue'),
        ('inventory', 'Inventory Issue'),
        ('address', 'Address Issue'),
        ('other', 'Other'),
    )
    
    code = models.CharField(max_length=50, unique=True)  # e.g., 'OUT_OF_STOCK'
    reason_text = models.CharField(max_length=200)  # e.g., 'Out of Stock'
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    customer_message = models.TextField(help_text="Message shown to customer")
    internal_note = models.TextField(blank=True, help_text="Internal note for admins only")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'reason_text']
        verbose_name_plural = "Rejection Reasons"
    
    def __str__(self):
        return f"{self.reason_text} ({self.get_category_display()})"


class RejectedOrder(models.Model):
    """
    Complete audit trail for rejected orders.
    Stores order snapshot, rejection reason, admin info, and timestamps.
    """
    # Core rejection data
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='rejection_record')
    rejection_reason = models.ForeignKey(RejectionReason, on_delete=models.SET_NULL, null=True, blank=True)
    custom_reason = models.TextField(blank=True, help_text="Custom rejection reason if admin typed instead of selecting predefined")
    
    # Admin who rejected
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='rejected_orders', limit_choices_to={'role__in': ['sales_admin', 'manager']})
    rejected_at = models.DateTimeField(auto_now_add=True)
    
    # Snapshot of order at time of rejection
    order_total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    order_item_count = models.PositiveIntegerField()
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    
    # Customer notification tracking
    customer_notified = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Appeals/follow-up
    can_appeal = models.BooleanField(default=True)
    appeal_requested = models.BooleanField(default=False)
    appeal_requested_at = models.DateTimeField(null=True, blank=True)
    appeal_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-rejected_at']
        indexes = [
            models.Index(fields=['order', '-rejected_at']),
            models.Index(fields=['rejection_reason', 'rejected_at']),
            models.Index(fields=['customer_email', '-rejected_at']),
        ]
    
    def __str__(self):
        return f"Rejected Order #{self.order.id} - {self.get_rejection_reason_display()}"
    
    def get_rejection_reason_display(self):
        """Get the display reason (predefined or custom)."""
        if self.custom_reason:
            return self.custom_reason
        return self.rejection_reason.reason_text if self.rejection_reason else "No reason provided"
    
    def get_customer_message(self):
        """Get the message shown to customer."""
        if self.custom_reason:
            return self.custom_reason
        return self.rejection_reason.customer_message if self.rejection_reason else "Your order was rejected."


AUDIT_CHAIN_GENESIS = 'ZARLY_AUDIT_CHAIN_V1'


class AuditLog(models.Model):
    """
    Immutable audit trail of every security-relevant action in the system.
    Supports the non-repudiation theme: every action is attributable to an actor,
    timestamped, and traceable to a source IP.

    Hash chaining: each row stores a SHA-256 of its own content plus the
    previous row's chain_hash. Deleting or altering any row breaks every
    subsequent hash, making tampering detectable via verify_chain().
    """
    ACTION_CHOICES = (
        ('order_created', 'Order Created'),
        ('order_approved', 'Order Approved'),
        ('order_rejected', 'Order Rejected'),
        ('order_prepared', 'Order Prepared'),
        ('order_ready_for_delivery', 'Marked Ready for Delivery'),
        ('order_out_for_delivery', 'Marked Out for Delivery'),
        ('order_delivered', 'Order Delivered'),
        ('payment_initiated', 'Payment Initiated'),
        ('payment_verified', 'Payment Verified'),
        ('payment_rejected', 'Payment Rejected'),
        ('payment_proof_uploaded', 'Payment Proof Uploaded'),
        ('signature_created', 'Digital Signature Created'),
        ('receipt_verified', 'Receipt Verification Performed'),
        ('complaint_submitted', 'Complaint Submitted'),
        ('complaint_resolved', 'Complaint Resolved'),
        ('login_success', 'Login Success'),
        ('login_failed', 'Login Failed'),
        ('logout', 'Logout'),
        ('tracking_updated', 'Tracking Number Updated'),
        ('inventory_updated', 'Inventory Updated'),
        ('product_added', 'Product Added'),
        ('refund_issued', 'Refund Issued'),
        ('refund_failed', 'Refund Failed'),
        ('refund_manual', 'Manual Refund Flagged'),
        ('refund_processed', 'Manual Refund Processed'),
        ('order_cancelled', 'Order Cancelled by Customer'),
    )

    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='audit_logs')
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    target_model = models.CharField(max_length=50, blank=True,
                                    help_text="e.g., 'Order', 'Payment', 'Complaint'")
    target_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    chain_hash = models.CharField(max_length=64, blank=True, db_index=True,
                                  help_text="SHA-256 of this entry's content chained with the previous entry's hash.")

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor', '-timestamp']),
            models.Index(fields=['action_type', '-timestamp']),
            models.Index(fields=['target_model', 'target_id']),
        ]

    def _compute_hash(self, prev_hash):
        import hashlib, json
        content = '|'.join([
            prev_hash,
            str(self.actor_id or ''),
            self.action_type,
            self.description,
            self.target_model,
            str(self.target_id or ''),
            json.dumps(self.metadata, sort_keys=True),
            self.ip_address or '',
        ])
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        import hashlib
        from django.db import transaction
        if not self.pk:
            with transaction.atomic():
                last = (AuditLog.objects
                        .select_for_update()
                        .only('chain_hash')
                        .order_by('id')
                        .last())
                if last and last.chain_hash:
                    prev_hash = last.chain_hash
                else:
                    prev_hash = hashlib.sha256(AUDIT_CHAIN_GENESIS.encode()).hexdigest()
                self.chain_hash = self._compute_hash(prev_hash)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @classmethod
    def verify_chain(cls):
        """
        Walk every entry in insertion order and recompute each chain_hash.
        Returns (is_valid: bool, broken_at_id: int|None).
        A broken chain means at least one entry was altered or deleted.
        """
        import hashlib
        genesis = hashlib.sha256(AUDIT_CHAIN_GENESIS.encode()).hexdigest()
        prev_hash = genesis
        first_unchained = None

        for entry in cls.objects.order_by('id').iterator(chunk_size=500):
            if not entry.chain_hash:
                # Pre-chain entry (created before this feature was added) — skip
                # but mark so callers know the chain only covers a subset.
                first_unchained = entry.id
                continue
            expected = entry._compute_hash(prev_hash)
            if entry.chain_hash != expected:
                return False, entry.id
            prev_hash = entry.chain_hash

        return True, first_unchained  # True = valid; first_unchained = oldest pre-chain id or None

    def __str__(self):
        who = self.actor.username if self.actor else 'system'
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.get_action_type_display()} by {who}"


class Notification(models.Model):
    """In-app notifications shown to users with a bell icon and unread counter."""
    TYPE_CHOICES = (
        ('order_update', 'Order Update'),
        ('payment', 'Payment'),
        ('delivery', 'Delivery'),
        ('complaint', 'Complaint'),
        ('admin_alert', 'Admin Alert'),
        ('system', 'System'),
    )

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True,
                            help_text="Optional URL to navigate to when clicked")
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='system')
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.recipient.username}: {self.title}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class Refund(models.Model):
    """
    Tracks every refund attempt — automatic (Stripe) or manual (bank transfer / DuitNow).
    Created on order rejection or complaint resolution with action_taken='refund'.
    """
    STATUS_CHOICES = (
        ('pending',    'Pending'),
        ('succeeded',  'Refund Issued'),
        ('failed',     'Failed'),
        ('manual',     'Manual Refund Required'),
    )
    SOURCE_CHOICES = (
        ('order_rejection',      'Order Rejection'),
        ('complaint',            'Customer Complaint'),
        ('customer_cancellation','Customer Cancellation'),
        ('webhook',              'Stripe Webhook'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='refunds')
    complaint = models.ForeignKey(Complaint, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='refund_record')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    stripe_refund_id = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='processed_refunds')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund #{self.id} — Order #{self.order.id} ({self.get_status_display()})"


class EmailTemplate(models.Model):
    """Reusable campaign email templates, created by managers."""
    name    = models.CharField(max_length=200)
    subject = models.CharField(max_length=500)
    # Supports {{customer_name}}, {{loyalty_tier}}, {{last_order_date}}, {{company_name}}
    body_html = models.TextField(help_text="HTML body. Use {{customer_name}}, {{loyalty_tier}}, {{last_order_date}}.")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='email_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active  = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class EmailCampaign(models.Model):
    """Records every bulk email blast sent by a sales admin or manager."""
    name      = models.CharField(max_length=200)
    template  = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True,
                                  related_name='campaigns')
    sent_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                  related_name='sent_campaigns')
    sent_at   = models.DateTimeField(auto_now_add=True)
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count       = models.PositiveIntegerField(default=0)
    skipped_count    = models.PositiveIntegerField(default=0)
    failed_count     = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Campaign '{self.name}' — {self.sent_at:%Y-%m-%d}"


class EmailLog(models.Model):
    """One row per email sent (or attempted) to a customer — used for rate limiting."""
    STATUS_CHOICES = (
        ('sent',    'Sent'),
        ('failed',  'Failed'),
        ('skipped', 'Skipped'),
    )
    customer  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_logs')
    campaign  = models.ForeignKey(EmailCampaign, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='logs')
    subject   = models.CharField(max_length=500)
    status    = models.CharField(max_length=10, choices=STATUS_CHOICES)
    reason    = models.CharField(max_length=300, blank=True)
    sent_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
        indexes  = [models.Index(fields=['customer', '-sent_at'])]

    def __str__(self):
        return f"EmailLog [{self.status}] → {self.customer.email} — {self.subject[:40]}"