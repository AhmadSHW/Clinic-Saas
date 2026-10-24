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
