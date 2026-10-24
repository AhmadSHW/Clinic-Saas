from django.utils import timezone

from appointments.models import Appointment
from tenants.testing import ClinicTestCase


class DashboardTests(ClinicTestCase):
    def test_counts_todays_appointments(self):
        self.login_as()
        Appointment.objects.create(
            clinic=self.clinic, patient=self.patient, doctor=self.doc,
            scheduled_at=timezone.localtime().replace(hour=12), status=Appointment.Status.CONFIRMED,
        )
        r = self.c.get("/en/dashboard/")
        self.assertEqual(r.context["appointments_today"], 1)

    def test_public_pages_render(self):
        for url in ["/en/", "/en/accounts-choice/", "/en/find-clinic/", "/en/accounts/login/"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)

    def test_doctor_sees_only_own_appointments(self):
        other = self.make_staff("Other", "o@a.com", "doctor")
        for doctor in (self.doc, other):
            Appointment.objects.create(
                clinic=self.clinic, patient=self.patient, doctor=doctor,
                scheduled_at=timezone.localtime().replace(hour=12), status=Appointment.Status.CONFIRMED,
            )
        self.login_as("d@a.com")
        r = self.c.get("/en/dashboard/")
        self.assertTrue(r.context["is_doctor_view"])
        self.assertEqual(r.context["appointments_today"], 1)

    def test_sidebar_brand_links_home(self):
        self.login_as()
        r = self.c.get("/en/patients/")
        self.assertContains(r, 'href="/en/" class="flex items-center gap-2 cursor-pointer')
        r = self.c.get("/ar/patients/")
        self.assertContains(r, 'href="/ar/" class="flex items-center gap-2 cursor-pointer')

    def test_landing_page_keeps_staff_signed_in(self):
        self.assertContains(self.c.get("/en/"), "Sign in")
        self.login_as()
        r = self.c.get("/en/")
        self.assertEqual(r.context["staff_user"], self.admin)
        self.assertContains(r, "Go to dashboard")
        self.assertNotContains(r, ">Sign in<")
        self.assertEqual(self.c.get("/en/dashboard/").status_code, 200)
