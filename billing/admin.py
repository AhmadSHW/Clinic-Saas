# billing/admin.py
from django.contrib import admin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("clinic", "amount", "status", "period_start", "period_end")
    list_filter = ("status",)