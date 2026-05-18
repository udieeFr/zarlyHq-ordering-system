from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Product, Category, Allergy, Favourite, CustomerProfile


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
    list_display = ('name', 'category', 'price', 'weight_grams', 'stock', 'is_available')
    list_filter = ('category', 'allergies', 'is_available')
    search_fields = ('name',)


@admin.register(Favourite)
class FavouriteAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'added_at')
    search_fields = ('customer__username', 'product__name')


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'loyalty_tier', 'total_spent', 'total_orders', 'is_vip')
    list_filter = ('loyalty_tier', 'is_vip')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('total_spent', 'total_orders')
