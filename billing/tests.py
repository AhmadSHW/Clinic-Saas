import hashlib
import hmac
import json
import time

from django.test import Client

from notifications.models import Notification
from tenants.models import Clinic
from tenants.testing import ClinicTestCase
from .models import Subscription

WEBHOOK_SECRET = "whsec_test"


class BillingTests(ClinicTestCase):
    def send_webhook(self, event_type, obj):
        """Posts a correctly signed Stripe event to the webhook."""
        payload = json.dumps({"id": "evt_1", "object": "event", "type": event_type, "data": {"object": obj}})
        timestamp = int(time.time())
        signature = hmac.new(
            WEBHOOK_SECRET.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
        ).hexdigest()
        with self.settings(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET):
            r = Client().post("/billing/webhook/", payload, content_type="application/json",
                              HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}")
        self.assertEqual(r.status_code, 200)

    def invoice(self, invoice_id, billing_reason="subscription_cycle"):
        return {
            "id": invoice_id, "object": "invoice", "customer": "cus_1", "billing_reason": billing_reason,
            "amount_due": 4900, "amount_paid": 4900,
            "lines": {"object": "list", "data": [
                {"object": "line_item", "period": {"start": 1798761600, "end": 1801440000}},  # 2027
            ]},
        }

    def test_unsigned_webhook_rejected(self):
        r = Client().post("/billing/webhook/", "{}", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_subscription_lifecycle(self):
        checkout = {"id": "cs_1", "object": "checkout.session", "client_reference_id": str(self.clinic.id),
                    "customer": "cus_1", "subscription": "sub_1"}
        self.send_webhook("checkout.session.completed", checkout)
        self.send_webhook("checkout.session.completed", checkout)  # Stripe retry
        self.clinic.refresh_from_db()
        self.assertEqual((self.clinic.plan, self.clinic.stripe_customer_id), (Clinic.PlanType.PRO, "cus_1"))
        self.assertEqual(Subscription.objects.count(), 1)

        # The first invoice is already recorded by checkout
        self.send_webhook("invoice.paid", self.invoice("in_first", billing_reason="subscription_create"))
        self.assertEqual(Subscription.objects.count(), 1)

        # Failed renewal: past due, admins told, access kept during retries
        self.send_webhook("invoice.payment_failed", self.invoice("in_2"))
        row = Subscription.objects.get(stripe_invoice_id="in_2")
        self.assertEqual(row.status, Subscription.Status.PAST_DUE)
        self.assertTrue(Notification.objects.filter(recipient=self.admin, title="Payment failed").exists())
        self.login_as()
        self.assertEqual(self.c.get("/en/dashboard/").status_code, 200)
        self.assertContains(self.c.get("/en/billing/"), "Your last payment failed")

        # Retry succeeded
        self.send_webhook("invoice.paid", self.invoice("in_2"))
        row.refresh_from_db()
        self.assertEqual(row.status, Subscription.Status.ACTIVE)
        self.assertEqual(row.period_start.year, 2027)

        # All retries failed: Stripe ends the subscription and the clinic is locked out
        self.send_webhook("invoice.payment_failed", self.invoice("in_3"))
        self.send_webhook("customer.subscription.deleted", {"id": "sub_1", "object": "subscription", "customer": "cus_1"})
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.plan, Clinic.PlanType.TRIAL)
        self.assertTrue(self.clinic.needs_subscription)
        self.assertEqual(Subscription.objects.get(stripe_invoice_id="in_3").status, Subscription.Status.CANCELLED)
        self.assertRedirects(self.c.get("/en/dashboard/"), "/en/billing/", fetch_redirect_response=False)

    def test_billing_page_shows_real_price(self):
        self.login_as()
        page = self.c.get("/en/billing/").content.decode()
        self.assertIn("$49", page)
        self.assertNotIn("$129", page)
        self.assertNotIn("Starter", page)
