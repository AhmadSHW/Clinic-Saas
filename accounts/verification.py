# accounts/verification.py
"""
Email confirmation for new clinic admins ("staff") and patient-portal signups ("portal").

1. Signup sends an HTML + plain-text email with one button pointing at
   accounts:confirm_email/<token>, built from settings.SITE_URL.
2. A GET on that URL only shows a page that POSTs back (auto-submitted by JavaScript,
   with a visible button as fallback). Mail providers pre-open links with GET to scan
   them, so a scanner can't use up the token or get logged in.
3. The POST confirms the account, logs that browser in and goes to its dashboard.
   The browser that signed up polls accounts:verification_status and logs in too.

Tokens are signed, not stored: they expire after TOKEN_MAX_AGE and are single-use
because confirming changes state (the staff user becomes verified; the pending
portal signup is consumed). Resending is limited to once per RESEND_COOLDOWN per account.
"""
import math
import time

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

TOKEN_MAX_AGE = 30 * 60  # seconds
RESEND_COOLDOWN = 60  # seconds

STAFF = "staff"
PORTAL = "portal"

VALID = "valid"
EXPIRED = "expired"
INVALID = "invalid"

_signer = signing.TimestampSigner(salt="clinic-saas-email-confirmation")


def make_token(kind, obj_id):
    return _signer.sign_object({"k": kind, "id": obj_id})


def read_token(token):
    """
    Returns (status, kind, obj_id). For an expired token the signature is still
    checked, so kind and obj_id are trustworthy and a new email can be offered.
    """
    try:
        try:
            data = _signer.unsign_object(token, max_age=TOKEN_MAX_AGE)
            status = VALID
        except signing.SignatureExpired:
            data = _signer.unsign_object(token)
            status = EXPIRED
        return status, data["k"], data["id"]
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return INVALID, None, None


# ---------- Finding the account behind a token ----------

def pending_account(kind, obj_id):
    """The unconfirmed account (StaffUser or PortalSignup) or None if it's gone or already confirmed."""
    if kind == STAFF:
        from .models import StaffUser

        return StaffUser.objects.filter(id=obj_id, is_active=True, is_email_verified=False).select_related("clinic").first()
    if kind == PORTAL:
        from patients.models import PortalSignup

        return PortalSignup.objects.filter(id=obj_id, clinic__is_active=True).select_related("clinic").first()
    return None


def confirm_account(kind, obj_id):
    """
    Confirms the account. Returns ("ok", StaffUser or Patient), ("used", None) when
    it was already confirmed or no longer exists, or ("unavailable", None) when the
    patient's clinic can't take portal users right now (trial ended).
    """
    account = pending_account(kind, obj_id)
    if account is None:
        return "used", None

    if kind == STAFF:
        account.is_email_verified = True
        account.save(update_fields=["is_email_verified"])
        return "ok", account

    from patients.utils import complete_portal_signup

    if account.clinic.needs_subscription:
        return "unavailable", None
    patient = complete_portal_signup(account)
    return ("ok", patient) if patient else ("used", None)


# ---------- Sending ----------

def _cooldown_key(kind, account):
    # Per person, not per row: re-registering on the portal makes a new signup row
    if kind == PORTAL:
        return f"confirm-email-sent:portal:{account.clinic_id}:{account.email.lower()}"
    return f"confirm-email-sent:staff:{account.id}"


def seconds_until_resend(kind, account):
    sent_at = cache.get(_cooldown_key(kind, account))
    if sent_at is None:
        return 0
    return max(0, math.ceil(RESEND_COOLDOWN - (time.time() - sent_at)))


def send_confirmation_email(kind, account):
    """
    Sends the confirmation email unless one went to this account in the last
    RESEND_COOLDOWN seconds. Returns True if it sent.
    """
    key = _cooldown_key(kind, account)
    if not cache.add(key, time.time(), RESEND_COOLDOWN):
        return False

    if kind == PORTAL:
        clinic = account.clinic.name
        intro_en = f"Someone created a patient account at {clinic} with this email address."
        intro_ar = f"قام شخص بإنشاء حساب مريض في {clinic} بهذا البريد الإلكتروني."
    else:
        intro_en = "Someone created a Clinic SaS account with this email address."
        intro_ar = "قام شخص بإنشاء حساب في Clinic SaS بهذا البريد الإلكتروني."

    context = {
        "name": account.full_name,
        "intro_en": intro_en,
        "intro_ar": intro_ar,
        # SITE_URL, not the request's host: the link must work from any device and inbox
        "url": settings.SITE_URL + reverse("accounts:confirm_email", args=[make_token(kind, account.id)]),
        "minutes": TOKEN_MAX_AGE // 60,
    }
    message = EmailMultiAlternatives(
        subject="Is this you? · هل هذا أنت؟ — Clinic SaS",
        body=render_to_string("emails/confirm_email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[account.email],
    )
    message.attach_alternative(render_to_string("emails/confirm_email.html", context), "text/html")
    try:
        message.send()
    except Exception:
        # Let them try again right away if sending failed
        cache.delete(key)
        raise
    return True
