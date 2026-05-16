from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('sales_admin', 'Sales Administrator'),
        ('manager', 'Manager'),
    )
    
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='customer', blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

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

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Allergy(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    weight_grams = models.IntegerField(default=0)
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_available = models.BooleanField(default=True)
    allergies = models.ManyToManyField(Allergy, blank=True)

    def __str__(self):
        return self.name


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
        completed = Order.objects.filter(
            customer=self.user,
            status__in=['approved', 'delivered']
        )
        self.total_orders = completed.count()
        self.total_spent = sum((o.total_amount for o in completed), start=0)
        latest = completed.order_by('-created_at').first()
        self.last_order_at = latest.created_at if latest else None
        if self.total_spent >= 5000:
            self.loyalty_tier = 'platinum'
        elif self.total_spent >= 2000:
            self.loyalty_tier = 'gold'
        elif self.total_spent >= 500:
            self.loyalty_tier = 'silver'
        else:
            self.loyalty_tier = 'bronze'
        self.save()