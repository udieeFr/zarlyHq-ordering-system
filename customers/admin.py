from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Product, Category, Allergy

admin.site.register(Category)
admin.site.register(Allergy)

class CustomUserAdmin(UserAdmin):
    model = User
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('email', 'role', 'phone_number')}),
    )

    fieldsets = UserAdmin.fieldsets + (
        ('Extra Fields', {'fields': ('role', 'phone_number')}),
    )
    
    list_display = ['username', 'email', 'role', 'is_staff']

admin.site.register(User, CustomUserAdmin)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'weight_grams', 'stock')
    list_filter = ('category', 'allergies')
    search_fields = ('name',) # Corrected comment