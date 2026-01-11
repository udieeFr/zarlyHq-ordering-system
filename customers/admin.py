from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Product

# Define a custom UserAdmin that knows about your extra fields (role, phone_number)
class UserAdmin(BaseUserAdmin):
    # Fieldsets controls the layout of the "Change User" page
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Role', {'fields': ('role',)}),  # <--- Add your custom role field here
    )
    
    # List display controls the columns in the user list
    list_display = ('username', 'email', 'role', 'phone_number', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email')

# Register your User model with this new, smarter Admin
admin.site.register(User, UserAdmin)
admin.site.register(Product)