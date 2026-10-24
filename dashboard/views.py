# dashboard/views.py
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import login_required_session
from accounts.models import StaffUser
from patients.models import Patient
from appointments.models import Appointment
from appointments.utils import day_range, today_range
from .charts import delta, sparkline


from django.utils.translation import gettext_lazy as _
from tenants.models import Clinic



def landing(request):
    """Public marketing landing page — shown to anyone, logged in or not."""
    # "icon" is a name from dashboard/templatetags/ui.py
    features = [
        {"icon": "file-text", "icon_class": "feature-icon--brand", "title": _("Patient records"),
         "description": _("A complete medical history for every patient — conditions, allergies, vitals, and every visit laid out on a clean timeline.")},
        {"icon": "calendar", "icon_class": "feature-icon--orange", "title": _("Appointments"),
         "description": _("A clickable month calendar with doctor filters and one-click scheduling, so the front desk never double-books.")},
        {"icon": "clock", "icon_class": "feature-icon--brand", "title": _("Waiting queue"),
         "description": _("See who is next in every room and call patients in with a single tap — no more shouting down the hallway.")},
        {"icon": "credit-card", "icon_class": "feature-icon--brand", "title": _("Billing"),
         "description": _("Plans, invoices, and payment methods in one place, so your practice stays financially clear without a spreadsheet.")},
        {"icon": "users", "icon_class": "feature-icon--orange", "title": _("Staff"),
         "description": _("Roles, availability, and your whole team at a glance — from physicians to front-desk and nursing.")},
        {"icon": "bell", "icon_class": "feature-icon--brand", "title": _("Notifications"),
         "description": _("Never miss a follow-up, a referral, or an update. Every important moment surfaces right where you work.")},
    ]
    return render(request, "dashboard/landing.html", {"features": features})
@login_required_session
def home(request):
    """Main dashboard page after login."""
    staff_user = request.staff_user
    Status = Appointment.Status
    now = timezone.now()
    today = timezone.localdate()

    appointments = Appointment.objects.filter(clinic=request.clinic)
    # Doctors see their own day; admins and reception see the whole clinic
    if staff_user.is_doctor:
        appointments = appointments.filter(doctor=staff_user)

    # One query for last week + the next week, bucketed per local day in Python
    window_start = day_range(today - timedelta(days=7))[0]
    window_end = day_range(today + timedelta(days=6))[1]
    per_day = defaultdict(Counter)
    for scheduled_at, status in appointments.filter(
        scheduled_at__gte=window_start, scheduled_at__lt=window_end
    ).values_list("scheduled_at", "status"):
        per_day[timezone.localdate(scheduled_at)][status] += 1

    def booked(day):
        """Appointments on a day, not counting cancelled ones."""
        return sum(per_day[day].values()) - per_day[day][Status.CANCELLED]

    past_week = [today - timedelta(days=offset) for offset in range(6, -1, -1)]  # oldest first, today last
    same_day_last_week = today - timedelta(days=7)

    # ---- Stat tiles: value, change vs a named period, 7-day trend ----
    appointments_today = booked(today)
    completed_today = per_day[today][Status.COMPLETED]

    queue = appointments.filter(status=Status.IN_QUEUE).select_related("patient", "doctor")
    first_check_in = queue.exclude(checked_in_at=None).order_by("checked_in_at").values_list("checked_in_at", flat=True).first()
    longest_wait_minutes = int((now - first_check_in).total_seconds() // 60) if first_check_in else None

    patients = Patient.objects.filter(clinic=request.clinic)
    week_start = day_range(past_week[0])[0]
    new_patient_days = Counter(
        timezone.localdate(created) for created in patients.filter(created_at__gte=week_start).values_list("created_at", flat=True)
    )

    # ---- Today by status (stacked bar) ----
    status_order = [Status.PENDING, Status.CONFIRMED, Status.IN_QUEUE, Status.COMPLETED, Status.CANCELLED]
    status_total = sum(per_day[today].values())
    status_labels = {
        Status.PENDING: _("Pending"), Status.CONFIRMED: _("Confirmed"), Status.IN_QUEUE: _("In queue"),
        Status.COMPLETED: _("Completed"), Status.CANCELLED: _("Cancelled"),
    }
    status_breakdown = [
        {"status": s.value, "label": status_labels[s], "count": per_day[today][s],
         # A plain string so Django's number localization can't turn it into "12,5" in CSS
         "percent": f"{per_day[today][s] * 100 / status_total:.2f}" if status_total else "0"}
        for s in status_order if per_day[today][s]
    ]

    # ---- Today's schedule with a "now" divider ----
    day_start, day_end = today_range()
    schedule = list(
        appointments.filter(scheduled_at__gte=day_start, scheduled_at__lt=day_end)
        .exclude(status=Status.CANCELLED).select_related("patient", "doctor").order_by("scheduled_at")
    )
    next_up = None
    for appt in schedule:
        appt.is_past = appt.scheduled_at < now or appt.status == Status.COMPLETED
        if next_up is None and appt.scheduled_at >= now and appt.status in (Status.PENDING, Status.CONFIRMED):
            next_up = appt
    if next_up:
        next_up.minutes_until = int((next_up.scheduled_at - now).total_seconds() // 60)
    # Index where the "Now" line goes: before the first appointment that isn't past
    now_index = next((i for i, appt in enumerate(schedule) if not appt.is_past), len(schedule))

    # ---- Next 7 days (columns, today emphasized) ----
    week = [{"day": today + timedelta(days=offset), "count": booked(today + timedelta(days=offset))} for offset in range(7)]
    week_max = max([d["count"] for d in week] + [1])
    for d in week:
        d["percent"] = round(d["count"] * 100 / week_max)
        d["is_peak"] = d["count"] == week_max and d["count"] > 0

    # ---- Doctors today (whole-clinic view only) ----
    doctors_today = []
    if not staff_user.is_doctor:
        doctors_today = list(
            StaffUser.objects.filter(clinic=request.clinic, role=StaffUser.Role.DOCTOR, is_active=True)
            .annotate(
                today_count=Count("appointments", filter=Q(
                    appointments__scheduled_at__gte=day_start, appointments__scheduled_at__lt=day_end,
                ) & ~Q(appointments__status=Status.CANCELLED)),
                waiting=Count("appointments", filter=Q(appointments__status=Status.IN_QUEUE)),
            )
            .order_by("-today_count", "full_name")[:5]
        )
        busiest = max([d.today_count for d in doctors_today] + [1])
        for doctor in doctors_today:
            doctor.load_percent = round(doctor.today_count * 100 / busiest)

    hour = timezone.localtime().hour
    greeting = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"

    context = {
        "clinic": request.clinic,
        "is_doctor_view": staff_user.is_doctor,
        "greeting": greeting,
        "comparison_day": same_day_last_week,
        # Stat tiles
        "appointments_today": appointments_today,
        "appointments_delta": delta(appointments_today, booked(same_day_last_week)),
        "appointments_trend": sparkline([booked(day) for day in past_week]),
        "in_queue_count": queue.count(),
        "longest_wait_minutes": longest_wait_minutes,
        "completed_today": completed_today,
        "completed_delta": delta(completed_today, per_day[same_day_last_week][Status.COMPLETED]),
        "completed_trend": sparkline([per_day[day][Status.COMPLETED] for day in past_week]),
        "total_patients": patients.count(),
        "new_patients_week": sum(new_patient_days.values()),
        "patients_trend": sparkline([new_patient_days[day] for day in past_week]),
        # Panels
        "status_breakdown": status_breakdown,
        "status_total": status_total,
        "todays_appointments": schedule,
        "now_index": now_index,
        "next_up": next_up,
        "next_in_queue": queue.order_by("queue_position")[:3],
        "week": week,
        "week_total": sum(d["count"] for d in week),
        "doctors_today": doctors_today,
        "recent_notifications": staff_user.notifications.order_by("-created_at")[:5],
    }
    return render(request, "dashboard/home.html", context)



def account_chooser(request):
    """Lets the visitor pick whether they're clinic staff or a patient
    before being routed to the right login flow."""
    return render(request, "dashboard/account_chooser.html")


def find_clinic(request):
    """
    Patient-side entry point: the patient doesn't know a 'slug', so they
    search for their clinic by name here, then get routed to that
    clinic's portal login/register page.
    """
    query = request.GET.get("q", "").strip()
    clinics = Clinic.objects.filter(is_active=True)

    if query:
        clinics = clinics.filter(name__icontains=query)
    else:
        clinics = clinics.none()

    return render(request, "dashboard/find_clinic.html", {
        "query": query,
        "clinics": clinics,
    })