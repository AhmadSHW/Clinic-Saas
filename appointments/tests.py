from django.utils import timezone

from tenants.testing import ClinicTestCase
from .models import Appointment


class AppointmentTests(ClinicTestCase):
    def make_appointment(self, status=Appointment.Status.CONFIRMED):
        return Appointment.objects.create(
            clinic=self.clinic, patient=self.patient, doctor=self.doc,
            scheduled_at=timezone.now(), status=status,
        )

    def test_state_changes_reject_get(self):
        self.login_as()
        appointment = self.make_appointment()
        self.assertEqual(self.c.get(f"/en/appointments/{appointment.id}/cancel/").status_code, 405)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_queue_positions_never_repeat(self):
        self.login_as()
        appts = [self.make_appointment() for _ in range(3)]
        self.c.post(f"/en/appointments/{appts[0].id}/check-in/")
        self.c.post(f"/en/appointments/{appts[1].id}/check-in/")
        self.c.post(f"/en/appointments/{appts[0].id}/complete/")
        self.c.post(f"/en/appointments/{appts[2].id}/check-in/")
        positions = [Appointment.objects.get(id=a.id).queue_position for a in appts]
        self.assertEqual(positions, [1, 2, 3])

    def test_cancelled_appointment_cannot_be_checked_in(self):
        self.login_as()
        appointment = self.make_appointment()
        self.c.post(f"/en/appointments/{appointment.id}/cancel/")
        self.c.post(f"/en/appointments/{appointment.id}/check-in/")
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)

    def test_booking_validates_date_and_doctor(self):
        self.login_as()
        url = "/en/appointments/book/"

        r = self.c.post(url, {"patient_id": self.patient.id, "doctor_id": self.doc.id, "scheduled_at": ""})
        self.assertEqual(r.status_code, 200)

        # An admin isn't a doctor
        r = self.c.post(url, {"patient_id": self.patient.id, "doctor_id": self.admin.id, "scheduled_at": "2030-01-01T10:00"})
        self.assertEqual(r.status_code, 404)

        r = self.c.post(url, {"patient_id": self.patient.id, "doctor_id": self.doc.id, "scheduled_at": "2030-01-01T10:00"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_pages_render(self):
        self.login_as()
        for url in ["/en/appointments/", "/en/appointments/queue/", "/en/appointments/book/"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)

    def test_list_filters_by_doctor_and_book_preselects(self):
        other = self.make_staff("Other", "o@a.com", "doctor")
        self.make_appointment()
        self.login_as()

        r = self.c.get(f"/en/appointments/?doctor={other.id}")
        self.assertEqual(r.context["filter_doctor"], other)
        self.assertEqual(len(r.context["appointments"]), 0)
        r = self.c.get(f"/en/appointments/?doctor={self.doc.id}")
        self.assertEqual(len(r.context["appointments"]), 1)
        # Not a doctor of this clinic
        self.assertEqual(self.c.get(f"/en/appointments/?doctor={self.admin.id}").status_code, 404)

        r = self.c.get(f"/en/appointments/book/?doctor={self.doc.id}")
        self.assertEqual(r.context["selected_doctor"], str(self.doc.id))
        self.assertContains(r, f'value="{self.doc.id}" selected')
