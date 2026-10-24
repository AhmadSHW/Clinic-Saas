import re
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from accounts.models import StaffUser
from appointments.models import Appointment
from notifications.models import Notification
from tenants.testing import ClinicTestCase, PASSWORD
from .models import Patient, MedicalRecord, PortalSignup


class MedicalRecordTests(ClinicTestCase):
    def test_only_doctors_and_admins_can_add_records(self):
        self.make_staff("Rec", "r@a.com", StaffUser.Role.RECEPTION)
        url = f"/en/patients/{self.patient.id}/"

        for email, allowed in [("r@a.com", False), ("d@a.com", True), ("a@a.com", True)]:
            client = Client()
            self.login_as(email, client=client)
            page = client.get(url)
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.context["can_write_records"], allowed)

            before = MedicalRecord.objects.count()
            client.post(url, {"diagnosis": "Flu"})
            self.assertEqual(MedicalRecord.objects.count(), before + (1 if allowed else 0), email)


class PatientSearchTests(ClinicTestCase):
    def test_search_by_name_phone_or_email(self):
        Patient.objects.create(clinic=self.clinic, full_name="Lina Haddad", phone_number="0599123", email="lina@x.com")
        self.login_as()
        for q in ["lina", "0599", "lina@x"]:
            r = self.c.get(f"/en/patients/?q={q}")
            self.assertEqual([p.full_name for p in r.context["patients"]], ["Lina Haddad"], q)
        r = self.c.get("/en/patients/?q=nobody")
        self.assertEqual(len(r.context["patients"]), 0)
        self.assertEqual(r.context["total_patients"], 2)


class PortalTests(ClinicTestCase):
    def test_login_with_duplicate_emails_and_cancel(self):
        # Staff can add several records with the same email; only one has a login
        Patient.objects.create(clinic=self.clinic, full_name="Dup", phone_number="2", email="p@p.com")
        patient = self.make_portal_patient("p@p.com")
        self.assertEqual(self.portal_login("p@p.com").status_code, 302)

        appointment = Appointment.objects.create(
            clinic=self.clinic, patient=patient, doctor=self.doc,
            scheduled_at=timezone.now() + timedelta(days=1), status=Appointment.Status.PENDING,
        )
        url = f"/en/patients/portal/appointments/{appointment.id}/cancel/"
        self.assertEqual(self.c.get(url).status_code, 405)
        self.c.post(url)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)
        self.assertTrue(Notification.objects.filter(
            recipient=self.doc, notification_type=Notification.NotificationType.APPOINTMENT_CANCELLED
        ).exists())

    def test_booking_page_renders_and_rejects_past_dates(self):
        self.make_portal_patient("q@q.com")
        self.portal_login("q@q.com")
        self.assertEqual(self.c.get("/en/patients/portal/book/").status_code, 200)
        r = self.c.post("/en/patients/portal/book/", {"doctor_id": self.doc.id, "scheduled_at": "2000-01-01T10:00"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Appointment.objects.exists())

    def test_closed_when_trial_expired(self):
        self.make_portal_patient("z@z.com")
        self.portal_login("z@z.com")
        self.expire_trial()

        r = self.c.get("/en/patients/portal/dashboard/")
        self.assertRedirects(r, "/en/", fetch_redirect_response=False)
        self.assertNotIn("patient_id", self.c.session)

        r = self.portal_login("z@z.com", client=Client())
        self.assertRedirects(r, "/en/", fetch_redirect_response=False)
        r = Client().get("/en/patients/portal/clinic-a/register/")
        self.assertRedirects(r, "/en/", fetch_redirect_response=False)


class PortalRegistrationTests(ClinicTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # the confirmation email's resend limit lives in the cache

    def register(self, client=None, **overrides):
        data = {"full_name": "Attacker", "email": "victim@p.com", "phone_number": "999",
                "password": PASSWORD, "confirm_password": PASSWORD}
        data.update(overrides)
        return (client or self.c).post("/en/patients/portal/clinic-a/register/", data)

    def link_from_last_email(self):
        """Path of the confirmation link (it's POSTed to confirm; a GET only shows a page)."""
        return re.search(r"https?://[^/\s]+(/\S+/confirm/\S+/)", mail.outbox[-1].body).group(1)

    def make_victim(self):
        return Patient.objects.create(clinic=self.clinic, full_name="Victim", phone_number="1", email="victim@p.com")

    def test_page_renders(self):
        self.assertEqual(self.c.get("/en/patients/portal/clinic-a/register/").status_code, 200)

    def test_unverified_registration_does_not_touch_existing_record(self):
        victim = self.make_victim()
        attacker = Client()
        r = self.register(client=attacker)
        self.assertRedirects(r, "/en/accounts/check-email/", fetch_redirect_response=False)
        self.assertNotIn("patient_id", attacker.session)

        victim.refresh_from_db()
        self.assertEqual((victim.full_name, victim.phone_number, victim.password_hash), ("Victim", "1", ""))

        # The attacker can't log in with the password they chose
        self.portal_login("victim@p.com", client=attacker)
        self.assertNotIn("patient_id", attacker.session)

    def test_verified_registration_links_existing_record(self):
        victim = self.make_victim()
        self.register(full_name="Real Victim", phone_number="555")
        link = self.link_from_last_email()

        r = self.c.post(link)
        self.assertRedirects(r, "/en/patients/portal/dashboard/", fetch_redirect_response=False)
        self.assertEqual(self.c.session["patient_id"], victim.id)
        victim.refresh_from_db()
        self.assertEqual(victim.full_name, "Real Victim")
        self.assertEqual(Patient.objects.filter(email="victim@p.com").count(), 1)

        # The link only works once
        other = Client()
        other.post(link)
        self.assertNotIn("patient_id", other.session)

        # The password chosen at registration works
        self.assertEqual(self.portal_login("victim@p.com", client=Client()).status_code, 302)

    def test_newer_link_invalidates_older_one(self):
        self.register(email="new@p.com", full_name="New")
        first = self.link_from_last_email()
        cache.clear()  # registering again more than 60 seconds later sends a new email
        self.register(email="new@p.com", full_name="New")
        second = self.link_from_last_email()
        self.assertNotEqual(first, second)
        self.assertFalse(Patient.objects.filter(email="new@p.com").exists())

        self.c.post(second)
        self.assertEqual(Patient.objects.filter(email="new@p.com").exclude(password_hash="").count(), 1)

        other = Client()
        other.post(first)
        self.assertNotIn("patient_id", other.session)


class CleanupPortalSignupsTests(ClinicTestCase):
    def make_signup(self, age):
        signup = PortalSignup.objects.create(
            clinic=self.clinic, email="s@s.com", full_name="S", phone_number="1", password_hash="x"
        )
        # created_at is auto_now_add, so backdate it with update()
        PortalSignup.objects.filter(id=signup.id).update(created_at=timezone.now() - age)
        return signup

    def test_deletes_only_expired_signups(self):
        old = self.make_signup(timedelta(hours=25))
        fresh = self.make_signup(timedelta(hours=1))

        out = StringIO()
        call_command("cleanup_portal_signups", stdout=out)

        self.assertFalse(PortalSignup.objects.filter(id=old.id).exists())
        self.assertTrue(PortalSignup.objects.filter(id=fresh.id).exists())
        self.assertIn("Deleted 1", out.getvalue())

    def test_dry_run_deletes_nothing(self):
        self.make_signup(timedelta(days=3))

        out = StringIO()
        call_command("cleanup_portal_signups", "--dry-run", stdout=out)

        self.assertEqual(PortalSignup.objects.count(), 1)
        self.assertIn("Would delete 1", out.getvalue())
