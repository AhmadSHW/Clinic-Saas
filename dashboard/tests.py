from datetime import timedelta

from django.template import Context, Template
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
        self.assertContains(r, 'href="/en/" class="flex items-center gap-2.5 cursor-pointer')
        r = self.c.get("/ar/patients/")
        self.assertContains(r, 'href="/ar/" class="flex items-center gap-2.5 cursor-pointer')

    def test_landing_page_keeps_staff_signed_in(self):
        self.assertContains(self.c.get("/en/"), "Sign in")
        self.login_as()
        r = self.c.get("/en/")
        self.assertEqual(r.context["staff_user"], self.admin)
        self.assertContains(r, "Go to dashboard")
        self.assertNotContains(r, ">Sign in<")
        self.assertEqual(self.c.get("/en/dashboard/").status_code, 200)

    def test_dashboard_week_chart_and_queue(self):
        Appointment.objects.create(
            clinic=self.clinic, patient=self.patient, doctor=self.doc,
            scheduled_at=timezone.now() + timedelta(days=2), status=Appointment.Status.CONFIRMED,
        )
        Appointment.objects.create(
            clinic=self.clinic, patient=self.patient, doctor=self.doc, queue_position=1,
            scheduled_at=timezone.now(), status=Appointment.Status.IN_QUEUE,
        )
        self.login_as()
        r = self.c.get("/en/dashboard/")
        self.assertEqual(len(r.context["week"]), 7)
        self.assertEqual(r.context["week"][0]["day"], timezone.localdate())
        self.assertGreaterEqual(r.context["week_total"], 1)
        self.assertEqual(len(r.context["next_in_queue"]), 1)
        self.assertIn(r.context["greeting"], ["morning", "afternoon", "evening"])

    def test_every_staff_page_renders_in_both_languages(self):
        self.login_as()
        for lang in ("en", "ar"):
            for path in ["dashboard/", "patients/", "patients/add/", f"patients/{self.patient.id}/",
                         "appointments/", "appointments/book/", "appointments/queue/",
                         "accounts/doctors/", "accounts/staff/", "accounts/staff/add/",
                         "accounts/settings/", "billing/", "notifications/"]:
                r = self.c.get(f"/{lang}/{path}")
                self.assertEqual(r.status_code, 200, f"/{lang}/{path}")

    def test_favicon(self):
        r = self.c.get("/favicon.ico")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith("favicon.svg"))

    def test_ui_template_helpers(self):
        out = Template(
            '{% icon "calendar" "h-4 w-4" %}|{{ "in_queue"|status_badge }}|{{ "Sara Ali"|initials }}|{{ "Sam"|initials }}'
        ).render(Context())
        svg, badge, two, one = out.split("|")
        self.assertIn('<svg', svg)
        self.assertIn('class="h-4 w-4"', svg)
        self.assertEqual((badge, two, one), ("badge-blue", "SA", "S"))

    def test_dashboard_tiles_breakdown_and_schedule(self):
        now = timezone.localtime()
        today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
        week_ago = today_noon - timedelta(days=7)
        for status in ["confirmed", "confirmed", "completed", "cancelled"]:
            Appointment.objects.create(clinic=self.clinic, patient=self.patient, doctor=self.doc,
                                       scheduled_at=today_noon, status=status)
        Appointment.objects.create(clinic=self.clinic, patient=self.patient, doctor=self.doc,
                                   scheduled_at=week_ago, status="completed")
        self.login_as()
        ctx = self.c.get("/en/dashboard/").context

        # Cancelled ones don't count as booked; 3 today vs 1 on the same day last week
        self.assertEqual(ctx["appointments_today"], 3)
        self.assertEqual(ctx["appointments_delta"], {"diff": 2, "direction": "up", "percent": 200})
        self.assertEqual(ctx["completed_delta"]["direction"], "flat")
        self.assertEqual(len(ctx["appointments_trend"]["points"].split()), 7)

        breakdown = {s["status"]: s["count"] for s in ctx["status_breakdown"]}
        self.assertEqual(breakdown, {"confirmed": 2, "completed": 1, "cancelled": 1})
        self.assertEqual(ctx["status_total"], 4)

        # The schedule hides cancelled visits; the Now line sits between past and upcoming
        self.assertEqual(len(ctx["todays_appointments"]), 3)
        self.assertLessEqual(ctx["now_index"], 3)
        self.assertEqual([d.full_name for d in ctx["doctors_today"]], ["Doc"])
        self.assertEqual(ctx["doctors_today"][0].today_count, 3)

    def test_doctor_dashboard_has_no_clinic_wide_panels(self):
        self.login_as("d@a.com")
        ctx = self.c.get("/en/dashboard/").context
        self.assertEqual(ctx["doctors_today"], [])


class ChartHelperTests(ClinicTestCase):
    def test_sparkline_and_delta(self):
        from .charts import delta, sparkline
        spark = sparkline([0, 2, 4])
        self.assertEqual(spark["points"].split()[0], "4.0,28.0")   # zero sits on the baseline
        self.assertEqual((spark["end_x"], spark["end_y"]), ("96.0", "4.0"))  # the max touches the top
        self.assertIsNone(sparkline([]))
        self.assertEqual(delta(5, 0), {"diff": 5, "direction": "up", "percent": None})
        self.assertEqual(delta(2, 4), {"diff": 2, "direction": "down", "percent": 50})
