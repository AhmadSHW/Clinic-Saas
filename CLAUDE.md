# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multi-tenant SaaS for small clinics/pharmacies (Django 5.2 + MySQL, server-rendered templates with Bootstrap 5 and vanilla JS, Stripe billing). English and Arabic UI. Comments in `config/settings.py` and some files are in Arabic.

## Commands

The virtualenv lives in `venv/` (Windows layout: `venv/Scripts/python.exe`).

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
python manage.py makemigrations <app>
python manage.py test                                   # all tests
python manage.py test appointments                      # one app
python manage.py test appointments.tests.SomeTestCase.test_method   # one test
python manage.py cleanup_portal_signups [--dry-run]     # delete expired pending patient signups (run daily)
```

Settings come from `.env` (see `.env.example`): `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` (comma-separated, defaults to localhost), `CSRF_TRUSTED_ORIGINS` (comma-separated full origins like `https://host`; empty by default), `DB_*` (MySQL), `STRIPE_*`, optionally `EMAIL_BACKEND` (defaults to the console backend, so verification emails print to the runserver log). There's no lint config.

Tests run against a temporary MySQL test database, so the DB user needs permission to create databases. Each app's `tests.py` builds on `tenants.testing.ClinicTestCase`, which sets up clinic `clinic-a` with an admin (`a@a.com`), a doctor (`d@a.com`) and a patient, plus helpers `login_as()`, `portal_login()`, `make_staff()`, `make_portal_patient()` and `expire_trial()`. `billing/tests.py` sends correctly signed Stripe webhooks, so webhook handlers can be tested without Stripe.

### Translations (Arabic)

```bash
python manage.py makemessages -l ar      # refresh locale/ar/LC_MESSAGES/django.po
python translate.py                      # fill msgstr from the dict in translate.py (needs polib, not in requirements.txt)
python manage.py compilemessages         # build django.mo
```

When you add a new `{% trans %}`/`gettext` string, add its Arabic translation to the `translations` dict in `translate.py`. All app URLs sit under `i18n_patterns` with `prefix_default_language=True`, so every page URL starts with `/en/` or `/ar/`. Language switching goes through `/i18n/`.

## Architecture

### Multi-tenancy (shared DB, shared schema)
- `tenants.Clinic` (UUID PK, unique `slug`) is the tenant. Every tenant-owned model has a `clinic` FK.
- `tenants.middleware.CurrentClinicMiddleware` sets `request.clinic` from `session["clinic_id"]`, or `None` if that clinic is missing or inactive.
- **Tenant isolation depends on views filtering every query by `clinic=request.clinic`.** Use `get_object_or_404(Model, id=..., clinic=request.clinic)`, never a bare lookup by id.
- Context processors expose `current_clinic` and `unread_notifications_count` to all templates.

### Authentication (custom, not `django.contrib.auth`)
There are two separate session-based identities:
- **Staff**: `accounts.StaffUser` (bcrypt `password_hash`, roles `admin`/`doctor`/`reception`, email unique per clinic only). Staff log in with clinic slug + email + password; login sets both `clinic_id` and `staff_user_id` in the session (and calls `session.cycle_key()`, as all logins should). Guard staff views with `accounts.decorators.login_required_session` (sets `request.staff_user`, scoped to `request.clinic`) or `@role_required("admin", ...)`, which already includes the login check. A new clinic is created through `accounts` signup, and the account is activated by an email verification link: a signed token from `accounts/utils.py`, valid 24 hours.
- **Patient portal**: `patients.Patient` logs in at `/patients/portal/<clinic_slug>/login/`. The session holds `patient_id`. Registration writes only a `PortalSignup` row (with the password already hashed) and emails a signed link (`patients/utils.py`, 24h). `portal_verify_email` creates the `Patient`, or attaches the login to a staff-created patient with the same email, and then deletes every pending signup for that email, so each link works once. Never write to `Patient` before the email is verified, or someone could take over a staff-created record just by knowing the patient's email. Guard portal views with `patients.decorators.login_required_patient` (sets `request.patient`, and its clinic is `request.patient.clinic`, not `request.clinic`).

`django.contrib.auth`/admin are installed but are not used for app users.

**Trial lockout:** `Clinic.needs_subscription` is true when the clinic is still on the trial plan and `trial_ends_at` has passed. When that's true, `login_required_session` sends admins to `billing:home` and shows other staff `accounts/trial_expired.html` (403). Views that must stay reachable are marked `@allow_expired_trial`, placed *below* `@role_required`/`@login_required_session` (currently the three billing views). The patient portal is closed too: `login_required_patient`, plus checks in portal login, register and verify. Every new staff view gets this behavior automatically through the decorators.

### Domain apps
- `appointments`: `Appointment` status flow is `pending`/`confirmed` → `in_queue` (check-in) → `completed`, or → `cancelled`. The views enforce these transitions. `queue_position` works like a ticket number: the highest position given to that doctor today, plus 1. `queue_view` shows the waiting queue. `appointments/utils.py` has `parse_scheduled_at` (form datetime → aware datetime or `None`) and `today_range`.
- `patients`: `Patient`, `MedicalRecord` (per-visit history), plus the patient portal views. Only doctors and admins can add medical records; `patient_detail` checks this on POST, and reception can only view them.
- `notifications`: internal-only `Notification` rows sent to a `StaffUser`. Views create them directly with `Notification.objects.create(...)` when appointments are booked or cancelled. There's no signals layer and no SMS.
- `billing`: Stripe Checkout creates the Pro subscription ($49/mo, `PRO_PLAN_PRICE_CENTS`). The webhook (`/billing/webhook/`, URL name `stripe_webhook`, registered in `config/urls.py` outside `i18n_patterns` so there's no language prefix; `csrf_exempt`) is the source of truth. Handlers are in `WEBHOOK_HANDLERS`:
  - `checkout.session.completed`: sets `Clinic.plan = PRO`, stores the Stripe customer/subscription IDs, and records the first payment. It finds the clinic through `client_reference_id`.
  - `invoice.paid` and `invoice.payment_failed`: find the clinic through `stripe_customer_id`. Each Stripe invoice gets one `Subscription` row, which moves between `active` and `past_due` as retries fail or succeed. Admins get a `Notification` when a payment fails, and keep access while Stripe retries.
  - `customer.subscription.deleted`: sets the plan back to `TRIAL` with `trial_ends_at` set to now, which triggers the same lockout as an expired trial.
  - Stripe event objects in stripe-python v15 are **not dicts** (`.get()` raises `AttributeError`). The webhook calls `.to_dict()` once and passes plain dicts to the handlers.
  - `billing:portal` sends admins to Stripe's hosted billing portal to update their card. The billing page price comes from `PRO_PLAN_PRICE_CENTS`.
  - Events to enable on the Stripe endpoint: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted`.
- `dashboard`: public landing page (`dashboard:landing`), clinic finder and account chooser, and the staff home (`dashboard:home`).

### Templates/static
Project-level `templates/base.html` (staff app shell) and `templates/public_base.html` (landing/portal). Each app has its own templates under `<app>/templates/<app>/`. Shared assets are `static/css/style.css` and `static/js/main.js`.

## Known gotchas
- `TIME_ZONE` is `Asia/Hebron`. Use `timezone.localdate()`/`localtime()`, not `timezone.now().date()`.
- **Don't use `__date` lookups** (e.g. `scheduled_at__date=today`). On MySQL without loaded time zone tables they silently match nothing. Use `today_range()` with `__gte`/`__lt` instead.
- Views that change state (check-in, cancel, complete, mark read) are `@require_POST` and are triggered by small `<form method="post">` + `{% csrf_token %}` buttons, not `<a href>` links. Keep it that way.
- In templates, a filter argument that doesn't exist raises an error (`{{ a|default:missing.attr }}` crashes, unlike `{{ missing.attr }}`). Use `{% if %}` instead.