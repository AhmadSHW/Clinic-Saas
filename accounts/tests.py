from datetime import timedelta

from email import message_from_bytes, policy
from email.message import EmailMessage as PyEmailMessage
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from tenants.models import Clinic
from tenants.testing import ClinicTestCase, PASSWORD
from patients.models import Patient, PortalSignup
from .email_replies import check_replies, make_token
from .models import StaffUser
from .utils import generate_verification_token


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

    def test_verify_link_logs_in_only_once(self):
        user = self.make_staff("New", "n@a.com", StaffUser.Role.ADMIN, is_email_verified=False)
        token = generate_verification_token(user.id)

        self.c.get(f"/en/accounts/verify/{token}/")
        self.assertEqual(self.c.session.get("staff_user_id"), user.id)

        other = Client()
        r = other.get(f"/en/accounts/verify/{token}/")
        self.assertRedirects(r, "/en/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn("staff_user_id", other.session)


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


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST_USER="clinic@gmail.com",
    EMAIL_HOST_PASSWORD="app-password",
    DEFAULT_FROM_EMAIL="clinic@gmail.com",
)
class ReplyVerificationTests(ClinicTestCase):
    """Verification by replying YES, with SMTP sending and the IMAP inbox faked."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.sent = []
        self.inbox = []
        patchers = [
            patch("django.core.mail.backends.smtp.EmailBackend.send_messages",
                  side_effect=lambda msgs: self.sent.extend(msgs) or len(msgs)),
            patch("accounts.email_replies.fetch_replies", side_effect=lambda: iter(self.inbox)),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def reply(self, body="Yes\n\nOn Fri, Clinic wrote:\n> quoted", sender=None, threaded=True, quote_ref=False):
        sent = self.sent[-1]
        msg = PyEmailMessage()
        msg["From"] = sender or sent.to[0]
        msg["Subject"] = "Re: " + sent.subject
        if threaded:
            msg["In-Reply-To"] = sent.extra_headers["Message-ID"]
        if quote_ref:
            body += "\n> " + sent.body.splitlines()[-1]
        msg.set_content(body)
        self.inbox.append(message_from_bytes(bytes(msg), policy=policy.default))

    def signup(self):
        return self.c.post("/en/accounts/signup/", {
            "clinic_name": "New", "clinic_slug": "new-clinic", "owner_email": "me@gmail.com",
            "admin_full_name": "Me", "admin_email": "me@gmail.com",
            "password": PASSWORD, "confirm_password": PASSWORD,
        })

    def status(self):
        return self.c.get("/en/accounts/verification-status/").json()

    def test_email_asks_for_reply_without_a_link(self):
        page = self.signup()
        self.assertTrue(page.context["by_reply"])
        sent = self.sent[-1]
        self.assertIn("reply YES to", sent.subject)
        self.assertNotIn("http", sent.body)
        self.assertEqual(sent.reply_to, ["clinic@gmail.com"])

    def test_yes_reply_verifies_and_waiting_page_logs_in(self):
        self.signup()
        self.assertFalse(self.status()["verified"])

        self.reply()
        cache.clear()  # skip the 10s throttle
        data = self.status()
        self.assertTrue(data["verified"])
        self.assertEqual(data["redirect"], "/en/dashboard/")
        user = StaffUser.objects.get(email="me@gmail.com")
        self.assertTrue(user.is_email_verified)
        self.assertEqual(self.c.session["staff_user_id"], user.id)

    def test_rejects_other_sender_or_other_answer(self):
        self.signup()
        self.reply(sender="attacker@evil.com")
        self.reply(body="No thanks")
        self.reply(body="Who is this?\n\nyes")
        check_replies()
        self.assertFalse(StaffUser.objects.get(email="me@gmail.com").is_email_verified)

    def test_forged_token_is_ignored(self):
        self.signup()
        msg = PyEmailMessage()
        msg["From"] = "me@gmail.com"
        msg["Subject"] = "Re: Clinic SaS: reply YES to verify your account"
        user = StaffUser.objects.get(email="me@gmail.com")
        msg["In-Reply-To"] = f"<{make_token('staff', user.id)}x@verify.clinicsaas>"
        msg.set_content("yes")
        self.inbox.append(message_from_bytes(bytes(msg), policy=policy.default))
        check_replies()
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)

    def test_login_checks_inbox(self):
        self.signup()
        self.reply(threaded=False, quote_ref=True)  # matched through the quoted Ref: line
        r = self.c.post("/en/accounts/login/", {"clinic_slug": "new-clinic", "email": "me@gmail.com", "password": PASSWORD})
        self.assertRedirects(r, "/en/dashboard/", fetch_redirect_response=False)

    def test_patient_portal_reply(self):
        self.c.post("/en/patients/portal/clinic-a/register/", {
            "full_name": "Pat", "email": "pat@gmail.com", "phone_number": "5",
            "password": PASSWORD, "confirm_password": PASSWORD,
        })
        self.assertIn("reply YES to", self.sent[-1].subject)
        self.reply(body="نعم")
        data = self.status()
        self.assertTrue(data["verified"])
        self.assertEqual(data["redirect"], "/en/patients/portal/dashboard/")
        self.assertTrue(Patient.objects.filter(email="pat@gmail.com").exclude(password_hash="").exists())
        self.assertFalse(PortalSignup.objects.exists())

    @override_settings(EMAIL_VERIFY_BY_REPLY=False)
    def test_switch_off_sends_a_link_instead(self):
        # For hosts where IMAP is blocked (PythonAnywhere free): Gmail still sends, with a link
        page = self.signup()
        self.assertFalse(page.context["by_reply"])
        self.assertIn("/en/accounts/verify/", self.sent[-1].body)
        self.assertNotIn("reply YES", self.sent[-1].subject)
