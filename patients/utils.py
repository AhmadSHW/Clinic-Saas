# patients/utils.py
from django.core import signing
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.urls import reverse

from accounts.email_replies import reply_verification_enabled, send_reply_verification_email

TOKEN_SALT = "clinic-saas-patient-email-verification"
TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours


def generate_signup_token(signup_id):
    return signing.dumps({"signup_id": signup_id}, salt=TOKEN_SALT)


def decode_signup_token(token):
    """Returns the PortalSignup id if the token is valid and not expired, else None."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        return data.get("signup_id")
    except signing.BadSignature:
        return None


def complete_portal_signup(signup):
    """
    Turns a verified PortalSignup into a Patient login and deletes every
    pending signup for that email, so each link/reply works only once.
    Returns the Patient, or None if this email already had an active login.
    """
    from .models import Patient, PortalSignup

    clinic = signup.clinic
    with transaction.atomic():
        pending = PortalSignup.objects.filter(clinic=clinic, email=signup.email)

        if Patient.objects.filter(clinic=clinic, email=signup.email).exclude(password_hash="").exists():
            pending.delete()
            return None

        patient = Patient.objects.filter(clinic=clinic, email=signup.email).first()
        if patient:
            # Staff had already added this patient manually (e.g. a walk-in).
            # The email is now proven, so link the portal login to that record.
            patient.full_name = signup.full_name
            patient.phone_number = signup.phone_number
        else:
            patient = Patient(clinic=clinic, email=signup.email,
                              full_name=signup.full_name, phone_number=signup.phone_number)
        patient.password_hash = signup.password_hash
        patient.save()

        pending.delete()
    return patient


def send_portal_verification_email(request, signup):
    if reply_verification_enabled():
        send_reply_verification_email(
            kind="portal",
            obj_id=signup.id,
            to=signup.email,
            subject=f"{signup.clinic.name}: reply YES to confirm your patient account",
            intro=(
                f"Hi {signup.full_name},\n\n"
                f"To finish creating your patient account at {signup.clinic.name}, "
                f"just reply to this email with the word YES."
            ),
        )
        return

    token = generate_signup_token(signup.id)
    verify_url = request.build_absolute_uri(
        reverse("patients:portal_verify_email", args=[token])
    )

    send_mail(
        subject=f"Confirm your {signup.clinic.name} patient account",
        message=(
            f"Hi {signup.full_name},\n\n"
            f"Please confirm your email address to finish creating your patient account at {signup.clinic.name}:\n"
            f"{verify_url}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"If you didn't request this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[signup.email],
        fail_silently=False,
    )
