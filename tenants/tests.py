from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Clinic


class NeedsSubscriptionTests(TestCase):
    def make_clinic(self, plan, trial_ends_at):
        return Clinic(name="A", slug="a", owner_email="o@a.com", plan=plan, trial_ends_at=trial_ends_at)

    def test_expired_trial_needs_subscription(self):
        clinic = self.make_clinic(Clinic.PlanType.TRIAL, timezone.now() - timedelta(days=1))
        self.assertTrue(clinic.needs_subscription)

    def test_running_trial_does_not(self):
        clinic = self.make_clinic(Clinic.PlanType.TRIAL, timezone.now() + timedelta(days=1))
        self.assertFalse(clinic.needs_subscription)

    def test_trial_without_end_date_does_not(self):
        self.assertFalse(self.make_clinic(Clinic.PlanType.TRIAL, None).needs_subscription)

    def test_pro_with_old_trial_date_does_not(self):
        clinic = self.make_clinic(Clinic.PlanType.PRO, timezone.now() - timedelta(days=30))
        self.assertFalse(clinic.needs_subscription)
