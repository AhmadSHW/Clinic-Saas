from datetime import timedelta

import re
import time
from unittest.mock import patch

from django.core import mail

from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from tenants.models import Clinic
from tenants.testing import ClinicTestCase, PASSWORD
from patients.models import Patient, PortalSignup
from . import verification
from .models import StaffUser


class LoginTests(ClinicTestCase):
    def test_login_works_in_fresh_browser(self):
        r = self.login_as()
        self.assertRedirects(r, "/en/dashboard/", fetch_redirect_response=False)
        self.assertEqual(self.c.get("/en/dashboard/").status_code, 200)

    def test_login_with_wrong_clinic_fails(self):
        r = self.c.post("/en/accounts/login/", {"clinic_slug": "nope", "email": "a@a.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("staff_user_id", self.c.session)


class SignupAndVerificationTests(ClinicTestCase):
    def test_signup_rejects_invalid_slug(self):
        self.c.post("/en/accounts/signup/", {
            "clinic_name": "B", "clinic_slug": "bad slug!", "owner_email": "b@b.com",
            "admin_full_name": "B", "admin_email": "b@b.com",
            "password": PASSWORD, "confirm_password": PASSWORD,
        })
        self.assertFalse(Clinic.objects.filter(name="B").exists())


class AddStaffTests(ClinicTestCase):
    def test_rejects_invalid_role_and_empty_password(self):
        self.login_as()
        self.c.post("/en/accounts/staff/add/", {"full_name": "X", "email": "x@a.com", "role": "superuser", "password": PASSWORD})
        self.c.post("/en/accounts/staff/add/", {"full_name": "X", "email": "x@a.com", "role": "doctor", "password": ""})
        self.assertFalse(StaffUser.objects.filter(email="x@a.com").exists())


class TrialLockoutTests(ClinicTestCase):
    def test_expired_trial_sends_admin_to_billing(self):
        self.expire_trial()
        self.login_as()
        self.assertRedirects(self.c.get("/en/dashboard/"), "/en/billing/", fetch_redirect_response=False)
        self.assertEqual(self.c.get("/en/patients/").status_code, 302)
        self.assertEqual(self.c.get("/en/billing/").status_code, 200)

        # Once upgraded, access returns
        self.clinic.plan = Clinic.PlanType.PRO
        self.clinic.save()
        self.assertEqual(self.c.get("/en/dashboard/").status_code, 200)

    def test_expired_trial_blocks_other_staff(self):
        self.expire_trial()
        self.login_as("d@a.com")
        r = self.c.get("/en/dashboard/")
        self.assertEqual(r.status_code, 403)
        self.assertTemplateUsed(r, "accounts/trial_expired.html")

        # Non-admin -> dashboard -> lockout page, without a redirect loop
        r = self.c.get("/en/billing/", follow=True)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(len(r.redirect_chain), 1)

    def test_running_trial_is_not_blocked(self):
        self.clinic.trial_ends_at = timezone.now() + timedelta(days=3)
        self.clinic.save()
        self.login_as()
        self.assertEqual(self.c.get("/en/dashboard/").status_code, 200)


class DoctorSectionTests(ClinicTestCase):
    def test_sidebar_knows_the_user_on_every_page(self):
        self.login_as()
        r = self.c.get("/en/appointments/")
        self.assertEqual(r.context["staff_user"], self.admin)
        self.assertContains(r, "/en/accounts/staff/")
        self.assertContains(r, "/en/accounts/doctors/")

    def test_admin_adds_doctor_who_can_then_log_in(self):
        self.login_as()
        page = self.c.get("/en/accounts/staff/add/?role=doctor")
        self.assertEqual(page.context["initial_role"], "doctor")

        r = self.c.post("/en/accounts/staff/add/", {
            "full_name": "New Doc", "email": "new@a.com", "role": "doctor",
            "specialty": "Dentist", "password": PASSWORD,
        })
        self.assertRedirects(r, "/en/accounts/doctors/", fetch_redirect_response=False)
        doctors = self.c.get("/en/accounts/doctors/").context["doctors"]
        self.assertIn("New Doc", [d.full_name for d in doctors])

        doctor_client = Client()
        self.login_as("new@a.com", client=doctor_client)
        self.assertEqual(doctor_client.get("/en/dashboard/").status_code, 200)
        # Doctors can see the doctors page but not add staff
        self.assertEqual(doctor_client.get("/en/accounts/doctors/").status_code, 200)
        self.assertNotEqual(doctor_client.get("/en/accounts/staff/add/").status_code, 200)

    def test_doctor_list_counts(self):
        from appointments.models import Appointment
        Appointment.objects.create(
            clinic=self.clinic, patient=self.patient, doctor=self.doc,
            scheduled_at=timezone.now() + timedelta(days=2), status=Appointment.Status.CONFIRMED,
        )
        self.login_as()
        doctor = self.c.get("/en/accounts/doctors/").context["doctors"].get(id=self.doc.id)
        self.assertEqual(doctor.upcoming_count, 1)


SITE = "https://aboshwiki.pythonanywhere.com"


@override_settings(SITE_URL=SITE)
class EmailConfirmationTests(ClinicTestCase):
    """Signup email with one button; GET shows a page, only POST confirms and logs in."""

    def setUp(self):
        super().setUp()
        cache.clear()  # the resend limit lives in the cache

    def signup(self, client=None, email="me@x.com"):
        return (client or self.c).post("/en/accounts/signup/", {
            "clinic_name": "New", "clinic_slug": "new-clinic", "owner_email": email,
            "admin_full_name": "Me", "admin_email": email,
            "password": PASSWORD, "confirm_password": PASSWORD,
        })

    def confirm_path(self):
        """Path of the button link, read from the plain-text part of the latest email."""
        return re.search(rf"{re.escape(SITE)}(/\S+/confirm/\S+/)", mail.outbox[-1].body).group(1)

    def new_admin(self):
        return StaffUser.objects.get(email="me@x.com")

    # ---------- The email ----------

    def test_signup_sends_html_and_text_email_built_from_site_url(self):
        r = self.signup()
        self.assertRedirects(r, "/en/accounts/check-email/", fetch_redirect_response=False)
        message = mail.outbox[-1]
        self.assertIn("Is this you?", message.subject)
        self.assertIn(SITE + "/en/accounts/confirm/", message.body)  # plain-text version has the link
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn(f'href="{SITE}/en/accounts/confirm/', html)
        self.assertIn("Yes, it's me", html)
        self.assertIn("نعم، هذا أنا", html)
        self.assertNotIn("127.0.0.1", message.body + html)

    def test_check_email_page_polls_and_counts_down_resend(self):
        self.signup()
        r = self.c.get("/en/accounts/check-email/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["poll"])
        self.assertEqual(r.context["email"], "me@x.com")
        self.assertGreater(r.context["resend_in"], 50)  # just sent, so resend is locked

    # ---------- Confirming ----------

    def test_get_does_not_verify(self):
        self.signup()
        scanner = Client()
        r = scanner.get(self.confirm_path())
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "accounts/confirm_email.html")
        self.assertFalse(self.new_admin().is_email_verified)
        self.assertNotIn("staff_user_id", scanner.session)
        # ...and the real click still works afterwards
        phone = Client()
        self.assertRedirects(phone.post(self.confirm_path()), "/en/dashboard/", fetch_redirect_response=False)

    def test_valid_token_logs_in_and_opens_dashboard(self):
        self.signup()
        phone = Client()
        r = phone.post(self.confirm_path())
        self.assertRedirects(r, "/en/dashboard/", fetch_redirect_response=False)
        self.assertTrue(self.new_admin().is_email_verified)
        self.assertEqual(phone.session["staff_user_id"], self.new_admin().id)
        self.assertEqual(phone.get("/en/dashboard/").status_code, 200)

    def test_waiting_page_logs_in_after_confirming_on_another_device(self):
        laptop = Client()
        self.signup(client=laptop)
        self.assertFalse(laptop.get("/en/accounts/check-email/status/").json()["verified"])

        Client().post(self.confirm_path())  # the phone
        data = laptop.get("/en/accounts/check-email/status/").json()
        self.assertEqual(data, {"verified": True, "redirect": "/en/dashboard/"})
        self.assertEqual(laptop.session["staff_user_id"], self.new_admin().id)

    def test_reused_token(self):
        self.signup()
        path = self.confirm_path()
        Client().post(path)
        again = Client()
        r = again.post(path)
        self.assertEqual(r.status_code, 410)
        self.assertEqual(r.context["status"], "used")
        self.assertFalse(r.context["can_resend"])
        self.assertNotIn("staff_user_id", again.session)
        self.assertEqual(Client().get(path).status_code, 410)

    def test_expired_token(self):
        self.signup()
        path = self.confirm_path()
        later = time.time() + verification.TOKEN_MAX_AGE + 60
        with patch("django.core.signing.time.time", return_value=later):
            r = Client().post(path)
            self.assertEqual(r.status_code, 410)
            self.assertEqual(r.context["status"], "expired")
            self.assertTrue(r.context["can_resend"])
            self.assertEqual(Client().get(path).context["status"], "expired")
        self.assertFalse(self.new_admin().is_email_verified)

    def test_expired_page_resends_a_working_email(self):
        self.signup()
        old_path = self.confirm_path()
        cache.clear()  # past the 60-second resend limit
        later = time.time() + verification.TOKEN_MAX_AGE + 60
        with patch("django.core.signing.time.time", return_value=later):
            r = Client().post(old_path + "resend/")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.context["poll"])
            new_path = self.confirm_path()
            self.assertNotEqual(new_path, old_path)
            self.assertRedirects(Client().post(new_path), "/en/dashboard/", fetch_redirect_response=False)

    def test_tampered_token(self):
        r = Client().get("/en/accounts/confirm/not-a-real-token/")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.context["status"], "invalid")

    # ---------- Resend limit ----------

    def test_resend_rate_limit(self):
        self.signup()
        self.assertEqual(len(mail.outbox), 1)

        r = self.c.post("/en/accounts/check-email/resend/", follow=True)
        self.assertEqual(len(mail.outbox), 1)  # blocked: sent less than 60 seconds ago
        self.assertIn("Please wait", str(list(r.context["messages"])[0]))

        cache.clear()  # 60 seconds later
        self.c.post("/en/accounts/check-email/resend/")
        self.assertEqual(len(mail.outbox), 2)
        self.c.post("/en/accounts/check-email/resend/")
        self.assertEqual(len(mail.outbox), 2)  # and blocked again

    def test_login_page_resend_form_is_rate_limited_and_generic(self):
        self.signup()
        cache.clear()
        for _ in range(3):
            r = Client().post("/en/accounts/resend-verification/", {"email": "ME@x.com"})
            self.assertRedirects(r, "/en/accounts/login/", fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 2)  # signup + one resend
        Client().post("/en/accounts/resend-verification/", {"email": "nobody@x.com"})
        self.assertEqual(len(mail.outbox), 2)

    def test_unconfirmed_admin_cannot_log_in(self):
        self.signup()
        r = Client().post("/en/accounts/login/", {"clinic_slug": "new-clinic", "email": "me@x.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "confirm your email")
        self.assertNotIn("staff_user_id", r.client.session)

    # ---------- Patient portal uses the same flow ----------

    def test_patient_portal_registration(self):
        laptop = Client()
        r = laptop.post("/en/patients/portal/clinic-a/register/", {
            "full_name": "Pat", "email": "pat@x.com", "phone_number": "5",
            "password": PASSWORD, "confirm_password": PASSWORD,
        })
        self.assertRedirects(r, "/en/accounts/check-email/", fetch_redirect_response=False)
        self.assertTemplateUsed(laptop.get("/en/accounts/check-email/"), "patients/portal_check_email.html")
        self.assertIn("patient account at A", mail.outbox[-1].body)

        path = self.confirm_path()
        Client().get(path)  # a scanner opening the link creates nothing
        self.assertFalse(Patient.objects.filter(email="pat@x.com").exists())
        phone = Client()
        self.assertRedirects(phone.post(path), "/en/patients/portal/dashboard/", fetch_redirect_response=False)
        patient = Patient.objects.get(email="pat@x.com")
        self.assertEqual(phone.session["patient_id"], patient.id)
        self.assertFalse(PortalSignup.objects.exists())
        self.assertTrue(laptop.get("/en/accounts/check-email/status/").json()["verified"])
        self.assertEqual(Client().post(path).status_code, 410)
