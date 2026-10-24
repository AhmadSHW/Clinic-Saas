# patients/management/commands/cleanup_portal_signups.py
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from patients.models import PortalSignup
from patients.utils import PENDING_SIGNUP_MAX_AGE


class Command(BaseCommand):
    help = (
        "Deletes patient portal signups that were never confirmed and are older than 24 hours. "
        "Safe to run any time, e.g. daily from cron / Task Scheduler."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many signups would be deleted.",
        )

    def handle(self, *args, **options):
        # Kept long enough for "Resend email" to work; after that they are abandoned
        cutoff = timezone.now() - timedelta(seconds=PENDING_SIGNUP_MAX_AGE)
        expired = PortalSignup.objects.filter(created_at__lt=cutoff)

        if options["dry_run"]:
            self.stdout.write(f"Would delete {expired.count()} expired portal signup(s).")
            return

        deleted, _ = expired.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired portal signup(s)."))
