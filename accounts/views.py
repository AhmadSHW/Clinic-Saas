# accounts/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from datetime import timedelta

from appointments.models import Appointment
from appointments.utils import today_range
from tenants.models import Clinic
from . import verification
from .models import StaffUser
from .decorators import login_required_session, role_required


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

            verification.send_confirmation_email(verification.STAFF, admin_user)

        # Lets this browser's "check your email" page log in once the email is confirmed
        # (even from another device). Only the browser that signed up has this.
        request.session["pending_verification"] = {
            "kind": verification.STAFF, "id": admin_user.id, "email": admin_user.email,
        }
        return redirect("accounts:check_email")

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

        if not staff_user.is_email_verified:
            messages.error(request, _("Please confirm your email before logging in. Check your inbox, or request a new email."))
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

# ============ Email confirmation (see accounts/verification.py) ============

def _log_in(request, kind, account):
    """Logs this browser in as the confirmed account and returns where to go next."""
    request.session.cycle_key()
    request.session.pop("pending_verification", None)
    messages.success(request, _("Your email is confirmed. Welcome, %(name)s!") % {"name": account.full_name})
    if kind == verification.STAFF:
        request.session["clinic_id"] = str(account.clinic_id)
        request.session["staff_user_id"] = account.id
        return reverse("dashboard:home")
    request.session["patient_id"] = account.id
    return reverse("patients:portal_dashboard")


def _pending_from_session(request):
    """(kind, unconfirmed account or None, pending dict) for this browser's own signup."""
    pending = request.session.get("pending_verification") or {}
    kind = pending.get("kind")
    if kind == verification.STAFF:
        return kind, verification.pending_account(kind, pending.get("id")), pending
    if kind == verification.PORTAL:
        from patients.models import PortalSignup

        signup = (PortalSignup.objects.filter(clinic_id=pending.get("clinic_id"), email=pending.get("email"))
                  .select_related("clinic").order_by("-created_at").first())
        return kind, signup, pending
    return None, None, pending


def check_email(request):
    """
    "Check your email" page shown after signup. It polls verification_status, so it
    logs in by itself when the button in the email is clicked, even on another device.
    """
    kind, account, pending = _pending_from_session(request)
    if not kind:
        return redirect("dashboard:account_chooser")
    context = {
        "email": pending["email"],
        "resend_in": verification.seconds_until_resend(kind, account) if account else 0,
        "poll": True,
    }
    if kind == verification.PORTAL:
        context["clinic"] = Clinic.objects.filter(id=pending["clinic_id"]).first()
        return render(request, "patients/portal_check_email.html", context)
    return render(request, "accounts/check_email.html", context)


def confirm_email(request, token):
    """
    Target of the button in the confirmation email.
    GET only shows a page that POSTs back by itself: mail providers pre-open links
    with GET to scan them, so a GET must never confirm or log anyone in.
    POST confirms the account, logs this browser in and opens the dashboard.
    """
    status, kind, obj_id = verification.read_token(token)
    if status != verification.VALID:
        return _confirm_problem(request, token, status, kind, obj_id)
    if verification.pending_account(kind, obj_id) is None:
        return _confirm_problem(request, token, "used", kind, obj_id)

    if request.method != "POST":
        return render(request, "accounts/confirm_email.html", {"token": token})

    result, account = verification.confirm_account(kind, obj_id)
    if result == "used":
        return _confirm_problem(request, token, "used", kind, obj_id)
    if result == "unavailable":
        messages.error(request, _("This clinic's patient portal is temporarily unavailable. Please contact the clinic."))
        return redirect("dashboard:landing")
    return redirect(_log_in(request, kind, account))


def _confirm_problem(request, token, status, kind, obj_id):
    """Friendly page for an expired, already-used or broken confirmation link."""
    account = verification.pending_account(kind, obj_id) if kind else None
    context = {
        "status": status,
        "token": token,
        "can_resend": account is not None,
        "resend_in": verification.seconds_until_resend(kind, account) if account is not None else 0,
        "kind": kind,
    }
    return render(request, "accounts/confirm_problem.html", context,
                  status=410 if status in ("expired", "used") else 400)


def verification_status(request):
    """
    Polled every few seconds by the "check your email" page. Once this browser's
    pending signup has been confirmed (here or on another device), logs it in.
    Only the browser that signed up has the pending entry, and it already knows
    the password, so this is no weaker than logging in.
    """
    pending = request.session.get("pending_verification")
    if not pending:
        return JsonResponse({"verified": False})

    if pending["kind"] == verification.STAFF:
        account = StaffUser.objects.filter(id=pending["id"], is_active=True, is_email_verified=True).first()
    else:
        from patients.models import Patient

        account = Patient.objects.filter(
            clinic_id=pending["clinic_id"], email=pending["email"], is_active=True
        ).exclude(password_hash="").first()

    if not account:
        return JsonResponse({"verified": False})
    return JsonResponse({"verified": True, "redirect": _log_in(request, pending["kind"], account)})


def _resend_message(request, sent, kind, account):
    if sent:
        messages.success(request, _("We sent you a new email. The button in it works for 30 minutes."))
    else:
        seconds = verification.seconds_until_resend(kind, account)
        messages.error(request, _("Please wait %(seconds)s seconds before asking for another email.") % {"seconds": seconds})


@require_POST
def resend_pending(request):
    """'Resend email' on the check-your-email page (this browser's own signup)."""
    kind, account, pending = _pending_from_session(request)
    if not kind:
        return redirect("dashboard:account_chooser")
    if account is not None:
        _resend_message(request, verification.send_confirmation_email(kind, account), kind, account)
    # If the account is already confirmed, the page's polling logs this browser in
    return redirect("accounts:check_email")


@require_POST
def resend_from_token(request, token):
    """'Resend email' on the expired/used link page."""
    status, kind, obj_id = verification.read_token(token)
    account = verification.pending_account(kind, obj_id) if status != verification.INVALID else None
    if account is None:
        return _confirm_problem(request, token, "used" if status != verification.INVALID else status, kind, obj_id)

    _resend_message(request, verification.send_confirmation_email(kind, account), kind, account)
    # No polling here: this browser opened a link, it didn't sign up, so it isn't logged in remotely
    return render(request, "accounts/check_email.html", {
        "email": account.email,
        "resend_in": verification.seconds_until_resend(kind, account),
        "poll": False,
        "resend_token": token,
    })


def resend_verification(request):
    """'Didn't get the confirmation email?' form on the login page (staff accounts)."""
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        # The same email can be unconfirmed in more than one clinic
        for staff_user in StaffUser.objects.filter(email__iexact=email, is_active=True, is_email_verified=False):
            verification.send_confirmation_email(verification.STAFF, staff_user)

        # Same answer whether or not the account exists, so emails can't be probed
        messages.success(request, _("If an unconfirmed account uses that email, we sent it a new confirmation email."))
        return redirect("accounts:login")

    return render(request, "accounts/resend_verification.html")
