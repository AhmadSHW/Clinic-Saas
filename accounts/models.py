# accounts/models.py
import bcrypt
from django.db import models
from tenants.models import Clinic


class StaffUser(models.Model):
    """
    A system user (staff member at a specific clinic) — either admin,
    doctor, or reception. Each user belongs to exactly one clinic (tenant).
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        DOCTOR = "doctor", "Doctor"
        RECEPTION = "reception", "Reception"

    clinic = models.ForeignKey(
        Clinic, on_delete=models.CASCADE, related_name="staff_members"
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    password_hash = models.CharField(max_length=255)

    role = models.CharField(max_length=15, choices=Role.choices, default=Role.RECEPTION)
    is_active = models.BooleanField(default=True)
    is_email_verified = models.BooleanField(default=True)

    # Doctor-specific field
    specialty = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Email must be unique within the same clinic only
        # (the same email can be used across two different clinics)
        unique_together = ("clinic", "email")
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()}) - {self.clinic.name}"

    def set_password(self, raw_password):
        """Hashes the password with bcrypt before saving."""
        hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt())
        self.password_hash = hashed.decode("utf-8")

    def check_password(self, raw_password):
        """Verifies the given password against the stored hash."""
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    @property
    def is_reception(self):
        return self.role == self.Role.RECEPTION