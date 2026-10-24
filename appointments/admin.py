# appointments/admin.py
from django.contrib import admin
from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "scheduled_at", "status", "clinic")
    list_filter = ("status", "clinic")
    search_fields = ("patient__full_name", "doctor__full_name")