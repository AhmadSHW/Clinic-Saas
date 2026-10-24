# accounts/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta

from appointments.models import Appointment
from appointments.utils import today_range
from tenants.models import Clinic
from .models import StaffUser
from .decorators import login_required_session, role_required
from .utils import send_verification_email, decode_verification_token
from .email_replies import check_replies, reply_verification_enabled


def clinic_signup(request):
    """
    Registers a brand new clinic AND its first admin user in one step.
    This is the entry point for a new tenant joining the platform.
    """
    if request.method == "POST":
        clinic_name = request.POST.get("clinic_name", "").strip()
        clinic_slug = request.POST.get("clinic_slug", "").strip().lower()
        owner_email = request.POST.get("owner_email", "").strip()
        admin_full_name = request.POST.get("admin_full_name", "").strip()
        admin_email = request.POST.get("admin_email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        errors = []

        if not all([clinic_name, clinic_slug, owner_email, admin_full_name, admin_email, password]):
            errors.append("All fields are required.")

        if password != confirm_password:
            errors.append("Passwords do not match.")

        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")

        if clinic_slug and clinic_slug != slugify(clinic_slug):
            errors.append("Clinic URL may only contain letters, numbers, and hyphens.")

        if Clinic.objects.filter(slug=clinic_slug).exists():
            errors.append("This clinic URL is already taken.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, "accounts/signup.html")

        # If the verification email fails to send, roll back so the slug isn't left taken
        with transaction.atomic():
            # Create the clinic (tenant) with a 14-day trial
            clinic = Clinic.objects.create(
                name=clinic_name,
                slug=clinic_slug,
                owner_email=owner_email,
                trial_ends_at=timezone.now() + timedelta(days=14),
            )

            # Create the first admin user for this clinic
            admin_user = StaffUser(
                clinic=clinic,
                full_name=admin_full_name,
                email=admin_email,
                role=StaffUser.Role.ADMIN,
                is_email_verified=False,
            )
            admin_user.set_password(password)
            admin_user.save()

            send_verification_email(request, admin_user)

        # Lets the "check your email" page log them in once they reply YES
        request.session["pending_verification"] = {"kind": "staff", "id": admin_user.id}
        return render(request, "accounts/check_email.html", {
            "email": admin_user.email,
            "by_reply": reply_verification_enabled(),
        })

    return render(request, "accounts/signup.html")


def login_view(request):
    """
    Logs a staff member into their clinic. The clinic is identified by its
    slug from the form, since the same email can exist in several clinics.
    """
    if request.method == "POST":
        clinic_slug = request.POST.get("clinic_slug", "").strip().lower()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        context = {"clinic_slug": clinic_slug}

        clinic = Clinic.objects.filter(slug=clinic_slug, is_active=True).first()
        staff_user = None
        if clinic:
            staff_user = StaffUser.objects.filter(
                clinic=clinic, email=email, is_active=True
            ).first()

        if not staff_user or not staff_user.check_password(password):
            messages.error(request, "Invalid clinic, email, or password.")
            return render(request, "accounts/login.html", context)

        if not staff_user.is_email_verified and check_replies():
            # They may have just replied YES to the verification email
            staff_user.refresh_from_db()

        if not staff_user.is_email_verified:
            messages.error(request, "Please verify your email before logging in. Check your inbox, or request a new email.")
            return render(request, "accounts/login.html", context)

        request.session.cycle_key()
        request.session["clinic_id"] = str(clinic.id)
        request.session["staff_user_id"] = staff_user.id
        messages.success(request, f"Welcome back, {staff_user.full_name}!")
        return redirect("dashboard:home")

    return render(request, "accounts/login.html")


def logout_view(request):
    request.session.pop("staff_user_id", None)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")


@role_required("admin")
def staff_list(request):
    """Only admins can view the full staff list for their clinic."""
    staff_members = StaffUser.objects.filter(clinic=request.clinic)
    return render(request, "accounts/staff_list.html", {"staff_members": staff_members})


@login_required_session
def doctor_list(request):
    """
    The clinic's doctors with today's and upcoming appointment counts.
    Every staff member can see it (reception books for doctors);
    only admins get the "Add doctor" button.
    """
    day_start, day_end = today_range()
    open_statuses = [
        Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.IN_QUEUE
    ]
    doctors = StaffUser.objects.filter(
        clinic=request.clinic, role=StaffUser.Role.DOCTOR
    ).annotate(
        today_count=Count("appointments", filter=Q(
            appointments__scheduled_at__gte=day_start,
            appointments__scheduled_at__lt=day_end,
            appointments__status__in=open_statuses + [Appointment.Status.COMPLETED],
        )),
        upcoming_count=Count("appointments", filter=Q(
            appointments__scheduled_at__gte=timezone.now(),
            appointments__status__in=open_statuses,
        )),
    )
    return render(request, "accounts/doctor_list.html", {"doctors": doctors})


@role_required("admin")
def add_staff(request):
    """Only admins can add new staff (doctor/reception) to their clinic."""
    # ?role=doctor (from the Doctors page) pre-selects the role
    context = {"initial_role": request.GET.get("role", StaffUser.Role.DOCTOR)}

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        role = request.POST.get("role", "")
        specialty = request.POST.get("specialty", "").strip()
        password = request.POST.get("password", "")

        errors = []
        if not full_name or not email:
            errors.append("Name and email are required.")
        if role not in StaffUser.Role.values:
            errors.append("Please choose a valid role.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if StaffUser.objects.filter(clinic=request.clinic, email=email).exists():
            errors.append("This email is already used in your clinic.")

        if errors:
            for error in errors:
                messages.error(request, error)
            context["initial_role"] = role
            return render(request, "accounts/add_staff.html", context)

        new_staff = StaffUser(
            clinic=request.clinic,
            full_name=full_name,
            email=email,
            role=role,
            specialty=specialty if role == StaffUser.Role.DOCTOR else "",
        )
        new_staff.set_password(password)
        new_staff.save()

        messages.success(request, f"{full_name} has been added successfully.")
        if new_staff.is_doctor:
            return redirect("accounts:doctors")
        return redirect("accounts:staff_list")

    return render(request, "accounts/add_staff.html", context)

@role_required("admin")
def clinic_settings(request):
    """Lets the clinic admin update basic clinic profile info."""
    clinic = request.clinic

    if request.method == "POST":
        if not request.POST.get("clinic_name", clinic.name).strip():
            messages.error(request, "Clinic name is required.")
            return render(request, "accounts/settings.html")

        clinic.name = request.POST.get("clinic_name", clinic.name).strip()
        clinic.owner_email = request.POST.get("owner_email", clinic.owner_email).strip()
        clinic.phone_number = request.POST.get("phone_number", clinic.phone_number).strip()
        clinic.address = request.POST.get("address", clinic.address).strip()
        clinic.save()

        messages.success(request, "Clinic settings updated.")
        return redirect("accounts:settings")

    return render(request, "accounts/settings.html")

def verify_email(request, token):
    staff_user_id = decode_verification_token(token)

    if not staff_user_id:
        messages.error(request, "This verification link is invalid or has expired.")
        return redirect("dashboard:account_chooser")

    try:
        staff_user = StaffUser.objects.get(id=staff_user_id, is_active=True)
    except StaffUser.DoesNotExist:
        messages.error(request, "Account not found.")
        return redirect("dashboard:account_chooser")

    request.session["clinic_id"] = str(staff_user.clinic.id)

    # The link only logs in once; otherwise it would work as a 24h login link
    if staff_user.is_email_verified:
        messages.info(request, "Your email is already verified. Please log in.")
        return redirect("accounts:login")

    staff_user.is_email_verified = True
    staff_user.save()

    request.session.cycle_key()
    request.session["staff_user_id"] = staff_user.id

    messages.success(request, f"Your email has been verified! Welcome, {staff_user.full_name}.")
    return redirect("dashboard:home")


def verification_status(request):
    """
    Polled by the "check your email" pages. Reads the inbox for a YES reply
    (at most every 10 seconds) and, once this browser's pending signup is
    verified, logs it in. Only the browser that signed up has the pending
    entry, and it already knows the password.
    """
    pending = request.session.get("pending_verification")
    if not pending:
        return JsonResponse({"verified": False})

    check_replies(throttle_seconds=10)

    if pending["kind"] == "staff":
        staff_user = StaffUser.objects.filter(
            id=pending["id"], is_active=True, is_email_verified=True
        ).select_related("clinic").first()
        if not staff_user:
            return JsonResponse({"verified": False})
        request.session.cycle_key()
        request.session["clinic_id"] = str(staff_user.clinic.id)
        request.session["staff_user_id"] = staff_user.id
        redirect_url = reverse("dashboard:home")
        messages.success(request, f"Your email has been verified! Welcome, {staff_user.full_name}.")
    else:
        from patients.models import Patient

        patient = Patient.objects.filter(
            clinic_id=pending["clinic_id"], email=pending["email"], is_active=True
        ).exclude(password_hash="").first()
        if not patient:
            return JsonResponse({"verified": False})
        request.session.cycle_key()
        request.session["patient_id"] = patient.id
        redirect_url = reverse("patients:portal_dashboard")
        messages.success(request, f"Your email is confirmed. Welcome, {patient.full_name}!")

    request.session.pop("pending_verification", None)
    return JsonResponse({"verified": True, "redirect": redirect_url})


def resend_verification(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        staff_user = StaffUser.objects.filter(email=email, is_email_verified=False).first()

        if staff_user:
            send_verification_email(request, staff_user)

        messages.success(request, "If an account with that email exists, a new verification email has been sent.")
        return redirect("accounts:login")

    return render(request, "accounts/resend_verification.html")