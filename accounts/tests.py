from datetime import timedelta

from django.test import Client
from django.utils import timezone

from tenants.models import Clinic
from tenants.testing import ClinicTestCase, PASSWORD
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
