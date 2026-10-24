# tenants/testing.py
from datetime import timedelta

from django.test import TestCase, Client, override_settings
from django.utils import timezone

from tenants.models import Clinic
from accounts.models import StaffUser
from patients.models import Patient

PASSWORD = "password123"


@override_settings(ALLOWED_HOSTS=["testserver"])
class ClinicTestCase(TestCase):
    """
    Shared fixture: one clinic ("clinic-a") with an admin, a doctor, and a
    staff-added patient. self.c is a fresh client; login_as() logs it in.
    """

    def setUp(self):
        self.clinic = Clinic.objects.create(name="A", slug="clinic-a", owner_email="o@a.com")
        self.admin = self.make_staff("Admin", "a@a.com", StaffUser.Role.ADMIN)
        self.doc = self.make_staff("Doc", "d@a.com", StaffUser.Role.DOCTOR)
        self.patient = Patient.objects.create(clinic=self.clinic, full_name="Pat", phone_number="1")
        self.c = Client()

    def make_staff(self, full_name, email, role, **extra):
        user = StaffUser(clinic=self.clinic, full_name=full_name, email=email, role=role, **extra)
        user.set_password(PASSWORD)
        user.save()
        return user

    def make_portal_patient(self, email, full_name="Portal Patient"):
        patient = Patient.objects.create(clinic=self.clinic, full_name=full_name, phone_number="1", email=email)
        patient.set_password(PASSWORD)
        patient.save()
        return patient

    def login_as(self, email="a@a.com", client=None):
        client = client or self.c
        return client.post("/en/accounts/login/", {"clinic_slug": "clinic-a", "email": email, "password": PASSWORD})

    def portal_login(self, email, client=None):
        client = client or self.c
        return client.post("/en/patients/portal/clinic-a/login/", {"email": email, "password": PASSWORD})

    def expire_trial(self):
        self.clinic.trial_ends_at = timezone.now() - timedelta(days=1)
        self.clinic.save()
