# appointments/models.py
from django.db import models
from tenants.models import Clinic
from accounts.models import StaffUser
from patients.models import Patient


class Appointment(models.Model):
    """A scheduled visit between a patient and a doctor at a clinic."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        IN_QUEUE = "in_queue", "In Queue"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="appointments")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
    doctor = models.ForeignKey(StaffUser, on_delete=models.SET_NULL, null=True, related_name="appointments")

    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    reason = models.CharField(max_length=255, blank=True)

    # Used for the real-time waiting queue on the day of the appointment
    queue_position = models.PositiveIntegerField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.patient.full_name} with Dr. {self.doctor.full_name if self.doctor else 'N/A'} at {self.scheduled_at}"