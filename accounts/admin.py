# accounts/admin.py
from django.contrib import admin
from .models import StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "role", "clinic", "is_active")
    list_filter = ("role", "is_active", "clinic")
    search_fields = ("full_name", "email")