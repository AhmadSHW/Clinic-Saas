# patients/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.decorators import login_required_session
from accounts.email_replies import check_replies, reply_verification_enabled
from accounts.models import StaffUser
from tenants.models import Clinic
from appointments.models import Appointment
from appointments.utils import parse_scheduled_at
from notifications.models import Notification
from .models import Patient, MedicalRecord, PortalSignup
from .decorators import login_required_patient
from .utils import send_portal_verification_email, decode_signup_token, complete_portal_signup


# ============ Staff-facing views ============

@login_required_session
def patient_list(request):
    patients = Patient.objects.filter(clinic=request.clinic)
    total_patients = patients.count()

    # ?q= comes from the search box in the top bar
    query = request.GET.get("q", "").strip()
    if query:
        patients = patients.filter(
            Q(full_name__icontains=query) | Q(phone_number__icontains=query) | Q(email__icontains=query)
        )

    context = {
        "patients": patients,
        "total_patients": total_patients,
        "query": query,
    }
    return render(request, "patients/list.html", context)


@login_required_session
def add_patient(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        email = request.POST.get("email", "").strip()
        date_of_birth = request.POST.get("date_of_birth") or None
        gender = request.POST.get("gender", "")
        blood_type = request.POST.get("blood_type", "").strip()
        allergies = request.POST.get("allergies", "").strip()

        if not full_name or not phone_number:
            messages.error(request, "Name and phone number are required.")
            return render(request, "patients/add.html")

        Patient.objects.create(
            clinic=request.clinic,
            full_name=full_name,
            phone_number=phone_number,
            email=email,
            date_of_birth=date_of_birth,
            gender=gender,
            blood_type=blood_type,
            allergies=allergies,
        )

        messages.success(request, f"Patient {full_name} added successfully.")
        return redirect("patients:list")

    return render(request, "patients/add.html")


@login_required_session
def patient_detail(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id, clinic=request.clinic)
    records = patient.medical_records.all()
    can_write_records = request.staff_user.is_doctor or request.staff_user.is_admin

    if request.method == "POST":
        if not can_write_records:
            messages.error(request, "Only doctors and admins can add medical records.")
            return redirect("patients:detail", patient_id=patient.id)

        diagnosis = request.POST.get("diagnosis", "").strip()
        prescription = request.POST.get("prescription", "").strip()
        notes = request.POST.get("notes", "").strip()

        if diagnosis:
            MedicalRecord.objects.create(
                patient=patient,
                doctor=request.staff_user if request.staff_user.is_doctor else None,
                diagnosis=diagnosis,
                prescription=prescription,
                notes=notes,
            )
            messages.success(request, "Medical record added.")
            return redirect("patients:detail", patient_id=patient.id)

    return render(request, "patients/detail.html", {
        "patient": patient,
        "records": records,
        "can_write_records": can_write_records,
    })


# ============ Patient portal views (self-service) ============

def _portal_unavailable(request):
    """The clinic's trial has ended, so its patient portal is closed."""
    messages.error(request, "This clinic's online portal is currently unavailable.")
    return redirect("dashboard:landing")


def portal_register(request, clinic_slug):
    clinic = get_object_or_404(Clinic, slug=clinic_slug, is_active=True)
    if clinic.needs_subscription:
        return _portal_unavailable(request)

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not all([full_name, email, phone_number, password]):
            messages.error(request, "All fields are required.")
            return render(request, "patients/portal_register.html", {"clinic": clinic})

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "patients/portal_register.html", {"clinic": clinic})

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, "patients/portal_register.html", {"clinic": clinic})

        if Patient.objects.filter(clinic=clinic, email=email).exclude(password_hash="").exists():
            messages.error(request, "An account with this email already exists. Please log in.")
            return render(request, "patients/portal_register.html", {"clinic": clinic})

        # Nothing touches Patient until the email is confirmed (see portal_verify_email)
        with transaction.atomic():
            signup = PortalSignup(
                clinic=clinic,
                email=email,
                full_name=full_name,
                phone_number=phone_number,
            )
            signup.set_password(password)
            signup.save()

            send_portal_verification_email(request, signup)

        # Lets the "check your email" page log them in once they reply YES
        request.session["pending_verification"] = {
            "kind": "portal", "clinic_id": str(clinic.id), "email": email,
        }
        return render(request, "patients/portal_check_email.html", {
            "clinic": clinic,
            "email": email,
            "by_reply": reply_verification_enabled(),
        })

    return render(request, "patients/portal_register.html", {"clinic": clinic})


def portal_verify_email(request, token):
    signup_id = decode_signup_token(token)
    signup = None
    if signup_id:
        signup = PortalSignup.objects.select_related("clinic").filter(
            id=signup_id, clinic__is_active=True
        ).first()

    # Missing signup = expired/tampered token, or a link that was already used
    if not signup:
        messages.error(request, "This verification link is invalid, expired, or already used.")
        return redirect("dashboard:find_clinic")

    clinic = signup.clinic
    if clinic.needs_subscription:
        return _portal_unavailable(request)

    patient = complete_portal_signup(signup)
    if not patient:
        # Another link for this email was confirmed first
        messages.info(request, "Your account is already active. Please log in.")
        return redirect("patients:portal_login", clinic_slug=clinic.slug)

    request.session.cycle_key()
    request.session["patient_id"] = patient.id
    messages.success(request, f"Your email is confirmed. Welcome, {patient.full_name}!")
    return redirect("patients:portal_dashboard")


def portal_login(request, clinic_slug):
    clinic = get_object_or_404(Clinic, slug=clinic_slug, is_active=True)
    if clinic.needs_subscription:
        return _portal_unavailable(request)

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        # Staff can add several records with the same email; only one can have a login
        patient = Patient.objects.filter(
            clinic=clinic, email=email, is_active=True
        ).exclude(password_hash="").first()

        if not patient and PortalSignup.objects.filter(clinic=clinic, email=email).exists() and check_replies():
            # They may have just replied YES to the verification email
            patient = Patient.objects.filter(
                clinic=clinic, email=email, is_active=True
            ).exclude(password_hash="").first()

        if not patient or not patient.check_password(password):
            messages.error(request, "Invalid email or password.")
            return render(request, "patients/portal_login.html", {"clinic": clinic})

        request.session.cycle_key()
        request.session["patient_id"] = patient.id
        messages.success(request, f"Welcome back, {patient.full_name}!")
        return redirect("patients:portal_dashboard")

    return render(request, "patients/portal_login.html", {"clinic": clinic})


def portal_logout(request):
    request.session.pop("patient_id", None)
    messages.info(request, "You have been logged out.")
    return redirect("dashboard:landing")


@login_required_patient
def portal_dashboard(request):
    patient = request.patient
    appointments = Appointment.objects.filter(patient=patient).exclude(
        status=Appointment.Status.CANCELLED
    ).order_by("scheduled_at")

    return render(request, "patients/portal_dashboard.html", {
        "patient": patient,
        "appointments": appointments,
    })


@login_required_patient
def portal_book_appointment(request):
    patient = request.patient
    doctors = StaffUser.objects.filter(
        clinic=patient.clinic, role=StaffUser.Role.DOCTOR, is_active=True
    )

    if request.method == "POST":
        doctor_id = request.POST.get("doctor_id")
        reason = request.POST.get("reason", "").strip()

        doctor = get_object_or_404(doctors, id=doctor_id)

        scheduled_at = parse_scheduled_at(request.POST.get("scheduled_at"))
        if not scheduled_at or scheduled_at < timezone.now():
            messages.error(request, "Please choose a valid date and time in the future.")
            return render(request, "patients/portal_book.html", {"patient": patient, "doctors": doctors})

        appointment = Appointment.objects.create(
            clinic=patient.clinic,
            patient=patient,
            doctor=doctor,
            scheduled_at=scheduled_at,
            reason=reason,
            status=Appointment.Status.PENDING,
        )

        Notification.objects.create(
            clinic=patient.clinic,
            recipient=doctor,
            patient=patient,
            notification_type=Notification.NotificationType.NEW_APPOINTMENT,
            title="New Appointment Request",
            message=f"{patient.full_name} requested an appointment on {appointment.scheduled_at.strftime('%Y-%m-%d %H:%M')}",
        )

        messages.success(request, "Your appointment request has been sent.")
        return redirect("patients:portal_dashboard")

    return render(request, "patients/portal_book.html", {"patient": patient, "doctors": doctors})


@require_POST
@login_required_patient
def portal_cancel_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.patient)

    if appointment.status not in (Appointment.Status.PENDING, Appointment.Status.CONFIRMED):
        messages.error(request, "This appointment can no longer be cancelled.")
        return redirect("patients:portal_dashboard")

    appointment.status = Appointment.Status.CANCELLED
    appointment.save()

    if appointment.doctor:
        Notification.objects.create(
            clinic=appointment.clinic,
            recipient=appointment.doctor,
            patient=request.patient,
            notification_type=Notification.NotificationType.APPOINTMENT_CANCELLED,
            title="Appointment Cancelled",
            message=f"{request.patient.full_name} cancelled their appointment on {timezone.localtime(appointment.scheduled_at).strftime('%Y-%m-%d %H:%M')}.",
        )

    messages.info(request, "Appointment cancelled.")
    return redirect("patients:portal_dashboard")