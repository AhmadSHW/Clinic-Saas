# tenants/models.py
import uuid
from django.db import models
from django.utils import timezone


class Clinic(models.Model):
    """Each registered clinic/pharmacy = an independent tenant."""

    class PlanType(models.TextChoices):
        TRIAL = "trial", "Trial"
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    owner_email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)

    plan = models.CharField(max_length=10, choices=PlanType.choices, default=PlanType.TRIAL)
    is_active = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def is_trial_expired(self):
        return bool(self.trial_ends_at and timezone.now() > self.trial_ends_at)

    @property
    def needs_subscription(self):
        """True when the clinic is locked out: still on trial and the trial has ended."""
        return self.plan == self.PlanType.TRIAL and self.is_trial_expired

    @property
    def is_subscribed(self):
        return self.plan != self.PlanType.TRIAL and self.is_active