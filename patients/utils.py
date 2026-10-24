# patients/utils.py
from django.core import signing
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

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


def send_portal_verification_email(request, signup):
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
