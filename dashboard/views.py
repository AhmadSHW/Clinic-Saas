# dashboard/views.py
from django.shortcuts import render

from accounts.decorators import login_required_session
from patients.models import Patient
from appointments.models import Appointment
from appointments.utils import today_range


from django.utils.translation import gettext_lazy as _
from tenants.models import Clinic



def landing(request):
    """Public marketing landing page — shown to anyone, logged in or not."""
    features = [
        {"icon": "👤", "icon_class": "feature-icon--teal", "title": _("Patient records"),
         "description": _("A complete medical history for every patient — conditions, allergies, vitals, and every visit laid out on a clean timeline.")},
        {"icon": "📅", "icon_class": "feature-icon--orange", "title": _("Appointments"),
         "description": _("A clickable month calendar with doctor filters and one-click scheduling, so the front desk never double-books.")},
        {"icon": "⏱", "icon_class": "feature-icon--teal", "title": _("Waiting queue"),
         "description": _("See who is next in every room and call patients in with a single tap — no more shouting down the hallway.")},
        {"icon": "💳", "icon_class": "feature-icon--teal", "title": _("Billing"),
         "description": _("Plans, invoices, and payment methods in one place, so your practice stays financially clear without a spreadsheet.")},
        {"icon": "👥", "icon_class": "feature-icon--orange", "title": _("Staff"),
         "description": _("Roles, availability, and your whole team at a glance — from physicians to front-desk and nursing.")},
        {"icon": "🔔", "icon_class": "feature-icon--teal", "title": _("Notifications"),
         "description": _("Never miss a follow-up, a referral, or an update. Every important moment surfaces right where you work.")},
    ]
    return render(request, "dashboard/landing.html", {"features": features})
@login_required_session
def home(request):
    """Main dashboard page after login."""
    day_start, day_end = today_range()
    todays_appointments = Appointment.objects.filter(
        clinic=request.clinic, scheduled_at__gte=day_start, scheduled_at__lt=day_end
    )
    context = {
        "staff_user": request.staff_user,
        "clinic": request.clinic,
        "total_patients": Patient.objects.filter(clinic=request.clinic).count(),
        "appointments_today": todays_appointments.count(),
        "in_queue_count": Appointment.objects.filter(
            clinic=request.clinic, status=Appointment.Status.IN_QUEUE
        ).count(),
        "todays_appointments": todays_appointments.order_by("scheduled_at")[:5],
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