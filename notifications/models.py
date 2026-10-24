# notifications/models.py
from django.db import models
from tenants.models import Clinic
from accounts.models import StaffUser
from patients.models import Patient


class Notification(models.Model):
    """
    An internal notification shown inside the system —
    to a staff member, about a patient/appointment event.
    No external SMS/WhatsApp service is used.
    """

    class NotificationType(models.TextChoices):
        APPOINTMENT_REMINDER = "appointment_reminder", "Appointment Reminder"
        NEW_APPOINTMENT = "new_appointment", "New Appointment"
        APPOINTMENT_CANCELLED = "appointment_cancelled", "Appointment Cancelled"
        WELCOME = "welcome", "Welcome"
        GENERAL = "general", "General"

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="notifications")

    # Who this notification is for (a staff member of the clinic)
    recipient = models.ForeignKey(
        StaffUser, on_delete=models.CASCADE, related_name="notifications"
    )

    # Optional link to the patient this notification is about
    patient = models.ForeignKey(
        Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )

    notification_type = models.CharField(max_length=25, choices=NotificationType.choices)
    title = models.CharField(max_length=150)
    message = models.TextField()

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} -> {self.recipient.full_name}"