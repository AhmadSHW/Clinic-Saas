# dashboard/views.py
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import login_required_session
from patients.models import Patient
from appointments.models import Appointment
from appointments.utils import day_range, today_range


from django.utils.translation import gettext_lazy as _
from tenants.models import Clinic



def landing(request):
    """Public marketing landing page — shown to anyone, logged in or not."""
    # "icon" is a name from dashboard/templatetags/ui.py
    features = [
        {"icon": "file-text", "icon_class": "feature-icon--teal", "title": _("Patient records"),
         "description": _("A complete medical history for every patient — conditions, allergies, vitals, and every visit laid out on a clean timeline.")},
        {"icon": "calendar", "icon_class": "feature-icon--orange", "title": _("Appointments"),
         "description": _("A clickable month calendar with doctor filters and one-click scheduling, so the front desk never double-books.")},
        {"icon": "clock", "icon_class": "feature-icon--teal", "title": _("Waiting queue"),
         "description": _("See who is next in every room and call patients in with a single tap — no more shouting down the hallway.")},
        {"icon": "credit-card", "icon_class": "feature-icon--teal", "title": _("Billing"),
         "description": _("Plans, invoices, and payment methods in one place, so your practice stays financially clear without a spreadsheet.")},
        {"icon": "users", "icon_class": "feature-icon--orange", "title": _("Staff"),
         "description": _("Roles, availability, and your whole team at a glance — from physicians to front-desk and nursing.")},
        {"icon": "bell", "icon_class": "feature-icon--teal", "title": _("Notifications"),
         "description": _("Never miss a follow-up, a referral, or an update. Every important moment surfaces right where you work.")},
    ]
    return render(request, "dashboard/landing.html", {"features": features})
@login_required_session
def home(request):
    """Main dashboard page after login."""
    day_start, day_end = today_range()
    appointments = Appointment.objects.filter(clinic=request.clinic)
    # Doctors see their own day; admins and reception see the whole clinic
    if request.staff_user.is_doctor:
        appointments = appointments.filter(doctor=request.staff_user)
    active = appointments.exclude(status=Appointment.Status.CANCELLED)
    todays_appointments = active.filter(scheduled_at__gte=day_start, scheduled_at__lt=day_end)
    queue = appointments.filter(status=Appointment.Status.IN_QUEUE).select_related("patient", "doctor")

    # Bar chart of the next 7 days (today first)
    week = []
    today = timezone.localdate()
    for offset in range(7):
        day = today + timedelta(days=offset)
        start, end = day_range(day)
        week.append({"day": day, "count": active.filter(scheduled_at__gte=start, scheduled_at__lt=end).count()})
    week_max = max([d["count"] for d in week] + [1])
    for d in week:
        d["percent"] = round(d["count"] * 100 / week_max)

    hour = timezone.localtime().hour
    greeting = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"

    context = {
        "clinic": request.clinic,
        "is_doctor_view": request.staff_user.is_doctor,
        "greeting": greeting,
        "total_patients": Patient.objects.filter(clinic=request.clinic).count(),
        "appointments_today": todays_appointments.count(),
        "completed_today": todays_appointments.filter(status=Appointment.Status.COMPLETED).count(),
        "in_queue_count": queue.count(),
        "next_in_queue": queue.order_by("queue_position")[:3],
        "todays_appointments": todays_appointments.select_related("patient", "doctor").order_by("scheduled_at")[:6],
        "week": week,
        "week_total": sum(d["count"] for d in week),
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