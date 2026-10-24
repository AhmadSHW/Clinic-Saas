# accounts/management/commands/check_verification_replies.py
from django.core.management.base import BaseCommand

from accounts.email_replies import check_replies, reply_verification_enabled


class Command(BaseCommand):
    help = (
        "Reads the inbox for YES replies to verification emails and activates "
        "those accounts. The website also checks on its own while someone waits "
        "on the 'check your email' page or tries to log in."
    )

    def handle(self, *args, **options):
        if not reply_verification_enabled():
            self.stdout.write("Reply verification is off (EMAIL_BACKEND is not SMTP, or no EMAIL_HOST_USER/PASSWORD).")
            return
        verified = check_replies()
        self.stdout.write(self.style.SUCCESS(f"Verified {verified} account(s)."))
