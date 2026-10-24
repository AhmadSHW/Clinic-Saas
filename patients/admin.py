# patients/admin.py
from django.contrib import admin
from .models import Patient, MedicalRecord


class MedicalRecordInline(admin.TabularInline):
    model = MedicalRecord
    extra = 0
    readonly_fields = ("visit_date",)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "clinic", "blood_type")
    list_filter = ("clinic", "gender")
    search_fields = ("full_name", "phone_number")
    inlines = [MedicalRecordInline]