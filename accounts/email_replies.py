# accounts/email_replies.py
"""
Email verification by reply: the email asks the user to reply "YES"
instead of clicking a link, and check_replies() reads the inbox over IMAP.

Each email carries a signed token (in its Message-ID, which the reply's
In-Reply-To/References point back to, and as a "Ref:" line that the reply
quotes). Only someone who received the email knows the token, and the reply
must come from the address being verified, so this is as safe as a link.

Used only when real SMTP sending is configured (see reply_verification_enabled);
with the console backend there is no inbox to reply to, so emails keep a link.
"""
import email
import imaplib
import logging
import re
from datetime import timedelta
from email import policy
from email.utils import parseaddr

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

TOKEN_SALT = "clinic-saas-reply-verification"
TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours
TOKEN_DOMAIN = "verify.clinicsaas"
# Every verification subject contains this, so IMAP can search for replies
SUBJECT_MARKER = "reply YES to"
YES_WORDS = {"yes", "y", "ok", "okay", "نعم", "ايوه", "أيوه", "اه"}

# "." can't appear in URL-safe base64, so it works as the signer separator
# and keeps the token valid inside a Message-ID
_signer = signing.TimestampSigner(salt=TOKEN_SALT, sep=".")
_TOKEN_RE = r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"
MESSAGE_ID_RE = re.compile(rf"<({_TOKEN_RE})@{re.escape(TOKEN_DOMAIN)}>")
REF_RE = re.compile(rf"Ref:\s*({_TOKEN_RE})")


def reply_verification_enabled():
    return (
        settings.EMAIL_VERIFY_BY_REPLY
        and settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
        and bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
    )


def make_token(kind, obj_id):
    return _signer.sign_object({"k": kind, "id": obj_id})


def read_token(token):
    """Returns (kind, id) for a valid, unexpired token, else None."""
    try:
        data = _signer.unsign_object(token, max_age=TOKEN_MAX_AGE)
        return data["k"], data["id"]
    except (signing.BadSignature, KeyError, TypeError):
        return None


def send_reply_verification_email(kind, obj_id, to, subject, intro):
    token = make_token(kind, obj_id)
    EmailMessage(
        subject=subject,
        body=(
            f"{intro}\n\n"
            f"You don't need to click anything. Just hit Reply, type YES and send.\n\n"
            f"This request expires in 24 hours. If you didn't sign up, you can ignore this email.\n\n"
            f"Ref: {token}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[settings.EMAIL_HOST_USER],
        headers={"Message-ID": f"<{token}@{TOKEN_DOMAIN}>"},
    ).send()


# ============ Reading replies ============

def _reply_text(msg):
    """The text the user typed: the reply body without the quoted original."""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = strip_tags(re.sub(r"<(br|/p|/div)[^>]*>", "\n", text, flags=re.I))
    lines = []
    for line in text.splitlines():
        # Gmail puts "On <date>, <name> wrote:" above the quoted original
        if line.startswith(">") or re.match(r"^\s*On .+wrote:\s*$", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _says_yes(msg):
    text = _reply_text(msg)
    if not text:
        return False
    first_word = re.split(r"[\s.,!؟?]+", text.lower(), maxsplit=1)[0]
    return first_word in YES_WORDS


def _tokens_in(msg):
    """Tokens from the threading headers first, then any quoted Ref: line."""
    headers = f"{msg.get('In-Reply-To', '')} {msg.get('References', '')}"
    tokens = MESSAGE_ID_RE.findall(headers)
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        tokens += REF_RE.findall(strip_tags(part.get_content()))
    return list(dict.fromkeys(tokens))


def _activate(kind, obj_id, sender):
    """Activates the account if it belongs to the reply's sender. Returns True if it did."""
    if kind == "staff":
        from .models import StaffUser

        staff_user = StaffUser.objects.filter(
            id=obj_id, is_active=True, is_email_verified=False
        ).first()
        if staff_user and staff_user.email.lower() == sender:
            staff_user.is_email_verified = True
            staff_user.save(update_fields=["is_email_verified"])
            return True

    elif kind == "portal":
        from patients.models import PortalSignup
        from patients.utils import complete_portal_signup

        signup = PortalSignup.objects.select_related("clinic").filter(
            id=obj_id, clinic__is_active=True
        ).first()
        if signup and signup.email.lower() == sender and not signup.clinic.needs_subscription:
            return complete_portal_signup(signup) is not None

    return False


def process_reply(msg):
    """Handles one inbox message. Returns True if it verified an account."""
    sender = parseaddr(msg.get("From", ""))[1].lower()
    if not sender or not _says_yes(msg):
        return False
    for token in _tokens_in(msg):
        found = read_token(token)
        if found and _activate(*found, sender):
            return True
    return False


def fetch_replies():
    """Yields recent inbox messages whose subject is one of ours (usually replies)."""
    since = (timezone.now() - timedelta(seconds=TOKEN_MAX_AGE)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(settings.EMAIL_IMAP_HOST, timeout=15) as imap:
        imap.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        # Read-only: the user's inbox isn't changed (nothing is marked read)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, f'(SINCE {since} SUBJECT "{SUBJECT_MARKER}")')
        for num in data[0].split():
            _, parts = imap.fetch(num, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                yield email.message_from_bytes(raw, policy=policy.default)


def check_replies(throttle_seconds=0):
    """
    Reads the inbox and verifies every account that got a YES reply.
    Returns how many were verified. With throttle_seconds, skips the check
    if one ran recently (pages poll this every few seconds).
    """
    if not reply_verification_enabled():
        return 0
    if throttle_seconds and not cache.add("email-replies-checked", True, throttle_seconds):
        return 0
    verified = 0
    try:
        for msg in fetch_replies():
            if process_reply(msg):
                verified += 1
    except (imaplib.IMAP4.error, OSError):
        logger.exception("Could not read verification replies from the inbox")
    return verified
