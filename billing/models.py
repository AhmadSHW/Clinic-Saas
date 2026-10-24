# billing/models.py
from django.db import models
from tenants.models import Clinic


class Subscription(models.Model):
    """
    Tracks the billing history for a clinic's subscription.
    One clinic can have multiple subscription records over time
    (renewals, plan changes, etc).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        CANCELLED = "cancelled", "Cancelled"

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="subscriptions")
    stripe_invoice_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.clinic.name} - {self.status} ({self.period_start.date()})"