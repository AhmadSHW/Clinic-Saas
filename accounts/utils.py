# accounts/utils.py
from django.core import signing
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse

TOKEN_SALT = "clinic-saas-email-verification"
TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours


def generate_verification_token(staff_user_id):
    return signing.dumps({"staff_user_id": staff_user_id}, salt=TOKEN_SALT)


def decode_verification_token(token):
    """Returns the staff_user_id if the token is valid and not expired, else None."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        return data.get("staff_user_id")
    except signing.BadSignature:
        return None


def send_verification_email(request, staff_user):
    token = generate_verification_token(staff_user.id)
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email", args=[token])
    )

    send_mail(
        subject="Verify your Clinic SaS account",
        message=(
            f"Hi {staff_user.full_name},\n\n"
            f"Please verify your email address to activate your Clinic SaS account:\n"
            f"{verify_url}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"If you didn't create this account, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[staff_user.email],
        fail_silently=False,
    )