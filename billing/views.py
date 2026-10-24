# billing/views.py (المنطق المصحح)
import stripe
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_timezone

from accounts.decorators import allow_expired_trial, login_required_session, role_required
from accounts.models import StaffUser
from notifications.models import Notification
from tenants.models import Clinic
from .models import Subscription

stripe.api_key = settings.STRIPE_SECRET_KEY

PRO_PLAN_PRICE_CENTS = 4900  # $49.00/month


@role_required("admin")
@allow_expired_trial
def billing_home(request):
    subscriptions = Subscription.objects.filter(clinic=request.clinic)
    return render(request, "billing/home.html", {
        "subscriptions": subscriptions,
        "pro_price": PRO_PLAN_PRICE_CENTS // 100,
        "has_past_due": subscriptions.filter(status=Subscription.Status.PAST_DUE).exists(),
    })


@role_required("admin")
@allow_expired_trial
def billing_portal(request):
    """Sends the admin to Stripe's hosted portal to update their card or cancel."""
    if not request.clinic.stripe_customer_id:
        messages.error(request, "Your clinic doesn't have a payment method on file yet.")
        return redirect("billing:home")

    portal_session = stripe.billing_portal.Session.create(
        customer=request.clinic.stripe_customer_id,
        return_url=request.build_absolute_uri("/billing/"),
    )
    return redirect(portal_session.url, permanent=False)


@role_required("admin")
@allow_expired_trial
def create_checkout_session(request):
    if request.clinic.plan == Clinic.PlanType.PRO:
        messages.info(request, "Your clinic is already on the Pro plan.")
        return redirect("billing:home")

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"{request.clinic.name} - Pro Plan (Monthly)"},
                "unit_amount": PRO_PLAN_PRICE_CENTS,
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }],
        mode="subscription",
        success_url=request.build_absolute_uri("/billing/success/"),
        cancel_url=request.build_absolute_uri("/billing/"),
        client_reference_id=str(request.clinic.id),
    )
    return redirect(checkout_session.url, permanent=False)


@login_required_session
@allow_expired_trial
def checkout_success(request):
    """
    Just a 'thank you' page. The actual upgrade happens in the webhook,
    not here, because this URL could otherwise be visited directly
    without any real payment.
    """
    messages.success(request, "Payment received! Your plan will be updated shortly.")
    return redirect("billing:home")


@csrf_exempt
def stripe_webhook(request):
    """
    The single source of truth for subscription status.
    Stripe calls this endpoint directly (server-to-server) whenever
    something happens with a payment or subscription.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    # stripe-python v15 objects aren't dicts; convert once so .get() works
    obj = event["data"]["object"].to_dict()
    handler = WEBHOOK_HANDLERS.get(event["type"])
    if handler:
        handler(obj)

    return HttpResponse(status=200)


def _handle_checkout_completed(session):
    clinic = Clinic.objects.filter(id=session.get("client_reference_id")).first()
    if not clinic:
        return  # Nothing to do, but acknowledge receipt

    clinic.plan = Clinic.PlanType.PRO
    clinic.stripe_customer_id = session.get("customer")
    clinic.stripe_subscription_id = session.get("subscription")
    clinic.save()

    # Stripe retries webhooks, so the same session can arrive more than once
    Subscription.objects.get_or_create(
        clinic=clinic,
        stripe_invoice_id=session.get("id", ""),
        defaults={
            "amount": PRO_PLAN_PRICE_CENTS / 100,
            "status": Subscription.Status.ACTIVE,
            "period_start": timezone.now(),
            "period_end": timezone.now() + timedelta(days=30),
        },
    )


def _handle_invoice_paid(invoice):
    """Records monthly renewals, and flips a past-due invoice back to paid after a successful retry."""
    if invoice.get("billing_reason") == "subscription_create":
        return  # The first payment is already recorded by checkout.session.completed

    clinic = _clinic_for_customer(invoice.get("customer"))
    if clinic:
        _record_invoice(clinic, invoice, Subscription.Status.ACTIVE, invoice.get("amount_paid", 0))


def _handle_invoice_payment_failed(invoice):
    """
    Stripe keeps retrying the card for a while, so the clinic keeps access
    for now; admins are told to update their payment method. If every retry
    fails, Stripe ends the subscription (customer.subscription.deleted).
    """
    clinic = _clinic_for_customer(invoice.get("customer"))
    if not clinic:
        return

    _record_invoice(clinic, invoice, Subscription.Status.PAST_DUE, invoice.get("amount_due", 0))
    _notify_admins(
        clinic,
        "Payment failed",
        "We couldn't charge your card for the Pro plan. Stripe will retry automatically; "
        "please update your payment method on the Billing page to avoid losing access.",
    )


def _handle_subscription_deleted(subscription):
    """
    The subscription ended (all payment retries failed, or it was cancelled).
    The clinic goes back to the trial plan with the trial already over, which
    locks it out like an expired trial until an admin subscribes again.
    """
    clinic = Clinic.objects.filter(stripe_subscription_id=subscription.get("id")).first()
    if not clinic:
        return  # An old subscription the clinic has since replaced

    clinic.plan = Clinic.PlanType.TRIAL
    clinic.stripe_subscription_id = None
    if not clinic.trial_ends_at or clinic.trial_ends_at > timezone.now():
        clinic.trial_ends_at = timezone.now()
    clinic.save()

    Subscription.objects.filter(clinic=clinic, status=Subscription.Status.PAST_DUE).update(
        status=Subscription.Status.CANCELLED
    )
    _notify_admins(
        clinic,
        "Subscription ended",
        "Your Pro subscription has ended. Subscribe again on the Billing page to restore access.",
    )


WEBHOOK_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


def _clinic_for_customer(customer_id):
    if not customer_id:
        return None
    return Clinic.objects.filter(stripe_customer_id=customer_id).first()


def _record_invoice(clinic, invoice, status, amount_cents):
    """One Subscription row per Stripe invoice, updated as its status changes."""
    period_start, period_end = timezone.now(), timezone.now() + timedelta(days=30)
    lines = (invoice.get("lines") or {}).get("data") or []
    if lines and lines[0].get("period"):
        period = lines[0]["period"]
        period_start = datetime.fromtimestamp(period["start"], tz=dt_timezone.utc)
        period_end = datetime.fromtimestamp(period["end"], tz=dt_timezone.utc)

    Subscription.objects.update_or_create(
        clinic=clinic,
        stripe_invoice_id=invoice.get("id", ""),
        defaults={
            "amount": amount_cents / 100,
            "status": status,
            "period_start": period_start,
            "period_end": period_end,
        },
    )


def _notify_admins(clinic, title, message):
    for admin in clinic.staff_members.filter(role=StaffUser.Role.ADMIN, is_active=True):
        Notification.objects.create(
            clinic=clinic,
            recipient=admin,
            notification_type=Notification.NotificationType.GENERAL,
            title=title,
            message=message,
        )