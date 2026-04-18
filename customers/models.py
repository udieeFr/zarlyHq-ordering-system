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
    allergies = models.ManyToManyField(Allergy, blank=True)

    def __str__(self):
        return self.name