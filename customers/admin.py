from django.contrib import admin
from .models import User, Product

# Customise how User looks in admin
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'phone_number', 'is_staff')
    list_filter = ('role',)
    search_fields = ('username', 'email')

admin.site.register(Product)