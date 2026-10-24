# patients/models.py
import bcrypt
from django.db import models
from tenants.models import Clinic
from accounts.models import StaffUser


class Patient(models.Model):
    """A patient record, scoped to a single clinic. Can optionally have
    portal login access (password_hash set) to book their own appointments."""

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="patients")
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    address = models.CharField(max_length=255, blank=True)

    # Basic medical info
    blood_type = models.CharField(max_length=5, blank=True)
    allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(blank=True)

    # Portal access (optional — a patient added by staff has no login
    # until they register themselves through the portal)
    password_hash = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} - {self.clinic.name}"

    def set_password(self, raw_password):
        hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt())
        self.password_hash = hashed.decode("utf-8")

    def check_password(self, raw_password):
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    @property
    def has_portal_access(self):
        return bool(self.password_hash)


class MedicalRecord(models.Model):
    """A single visit/record entry for a patient, written by a doctor."""

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medical_records")
    doctor = models.ForeignKey(StaffUser, on_delete=models.SET_NULL, null=True, related_name="written_records")

    visit_date = models.DateTimeField(auto_now_add=True)
    diagnosis = models.TextField()
    prescription = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-visit_date"]

    def __str__(self):
        return f"Record for {self.patient.full_name} on {self.visit_date.date()}"


class PortalSignup(models.Model):
    """
    A portal registration waiting for email verification. Nothing is written
    to Patient until the emailed link is clicked, so knowing someone's email
    isn't enough to take over a record staff created for them.
    """

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="portal_signups")
    email = models.EmailField()
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    password_hash = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pending signup {self.email} - {self.clinic.name}"

    def set_password(self, raw_password):
        hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt())
        self.password_hash = hashed.decode("utf-8")