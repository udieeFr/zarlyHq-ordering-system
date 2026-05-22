from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('sales_admin', 'Sales Administrator'),
        ('manager', 'Manager'),
    )
    
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='customer', blank=True, null=True, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def is_manager(self):
        """Check if user is a manager or superuser"""
        return self.role == 'manager' or self.is_superuser
    
    def is_sales_admin(self):
        """Check if user is a sales admin, manager, or superuser"""
        return self.role in ['sales_admin', 'manager'] or self.is_superuser
    
    def is_customer(self):
        """Check if user is a customer"""
        return self.role == 'customer'

class Allergy(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    weight_grams = models.IntegerField(default=0)
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_available = models.BooleanField(default=True, db_index=True)
    is_unlimited_stock = models.BooleanField(default=False)
    allergies = models.ManyToManyField(Allergy, blank=True)

    bundle_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bundle_quantity = models.IntegerField(null=True, blank=True)
    bundle_weight_grams = models.IntegerField(null=True, blank=True)
    bundle_stock = models.IntegerField(null=True, blank=True)

    @property
    def has_bundle(self):
        return self.bundle_price is not None

    @staticmethod
    def format_weight(grams):
        if not grams:
            return None
        return f"{grams // 1000}kg" if grams >= 1000 else f"{grams}g"

    def __str__(self):
        return self.name


class Favourite(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favourites')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favourited_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'product')

    def __str__(self):
        return f"{self.customer.username} → {self.product.name}"


class CustomerProfile(models.Model):
    """
    Extended CRM data for customers. Tracks lifetime value, loyalty tier,
    preferences, and admin notes. Auto-maintained on order events.
    """
    LOYALTY_TIER_CHOICES = (
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile',
                                limit_choices_to={'role': 'customer'})
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_order_at = models.DateTimeField(null=True, blank=True)
    loyalty_tier = models.CharField(max_length=20, choices=LOYALTY_TIER_CHOICES, default='bronze')
    marketing_opt_in = models.BooleanField(default=True)
    preferred_payment_method = models.CharField(max_length=50, blank=True)
    default_phone = models.CharField(max_length=20, blank=True)
    default_address = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True, help_text="Internal CRM notes — not visible to customer")
    is_vip = models.BooleanField(default=False, help_text="VIP/priority customer flag — surfaces orders at top of queue")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['loyalty_tier', '-total_spent']),
            models.Index(fields=['-last_order_at']),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.get_loyalty_tier_display()} (RM {self.total_spent})"

    def recalculate(self):
        """Recompute totals from order history. Call after order approval/delivery."""
        from admins.models import Order
        from django.db.models import Sum, Max, Count
        completed = Order.objects.filter(
            customer=self.user,
            status__in=['approved', 'delivered']
        )
        agg = completed.aggregate(
            total=Sum('total_amount'),
            count=Count('id'),
            latest=Max('created_at'),
        )
        self.total_orders = agg['count'] or 0
        self.total_spent = agg['total'] or 0
        self.last_order_at = agg['latest']
        if self.total_spent >= 5000:
            self.loyalty_tier = 'platinum'
        elif self.total_spent >= 2000:
            self.loyalty_tier = 'gold'
        elif self.total_spent >= 500:
            self.loyalty_tier = 'silver'
        else:
            self.loyalty_tier = 'bronze'
        self.save()


class OrderRating(models.Model):
    """Customer rates a delivered order (1–5 stars + optional comment)."""
    order = models.OneToOneField(
        'admins.Order', on_delete=models.CASCADE, related_name='rating'
    )
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_ratings')
    rating = models.PositiveSmallIntegerField()  # 1–5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['customer', '-created_at'])]

    def __str__(self):
        return f"Rating {self.rating}/5 for Order #{self.order_id} by {self.customer}"


class ProductReview(models.Model):
    """Customer reviews an individual product after a delivered order."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_reviews')
    order = models.ForeignKey(
        'admins.Order', on_delete=models.SET_NULL, null=True, related_name='product_reviews'
    )
    rating = models.PositiveSmallIntegerField()  # 1–5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'customer', 'order')
        indexes = [models.Index(fields=['product', '-created_at'])]

    def __str__(self):
        return f"Review {self.rating}/5 for {self.product} by {self.customer}"


