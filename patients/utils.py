# patients/utils.py
from django.db import transaction

# Unconfirmed portal signups are kept this long (so "Resend email" still works after
# the 30-minute link expires), then cleanup_portal_signups deletes them.
PENDING_SIGNUP_MAX_AGE = 60 * 60 * 24  # 24 hours


def complete_portal_signup(signup):
    """
    Turns a confirmed PortalSignup into a Patient login and deletes every
    pending signup for that email, so each confirmation link works only once.
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
