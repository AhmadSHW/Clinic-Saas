# patients/management/commands/cleanup_portal_signups.py
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from patients.models import PortalSignup
from patients.utils import TOKEN_MAX_AGE


class Command(BaseCommand):
    help = (
        "Deletes pending patient portal signups whose verification link has expired. "
        "Safe to run any time, e.g. daily from cron / Task Scheduler."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many signups would be deleted.",
        )

    def handle(self, *args, **options):
        # Older than the link lifetime = the link can no longer be used
        cutoff = timezone.now() - timedelta(seconds=TOKEN_MAX_AGE)
        expired = PortalSignup.objects.filter(created_at__lt=cutoff)

        if options["dry_run"]:
            self.stdout.write(f"Would delete {expired.count()} expired portal signup(s).")
            return

        deleted, _ = expired.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired portal signup(s)."))
