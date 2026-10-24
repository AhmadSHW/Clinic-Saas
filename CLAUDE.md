# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multi-tenant SaaS for small clinics/pharmacies (Django 5.2 + MySQL, server-rendered templates with Tailwind CSS 3 and vanilla JS, Stripe billing). English and Arabic UI. Comments in `config/settings.py` and some files are in Arabic.

## Commands

The virtualenv lives in `venv/` (Windows layout: `venv/Scripts/python.exe`).

```bash
pip install -r requirements-local.txt                  # requirements.txt (server) + mysqlclient + polib
python manage.py migrate
python manage.py runserver
python manage.py makemigrations <app>
python manage.py test                                   # all tests
python manage.py test appointments                      # one app
python manage.py test appointments.tests.SomeTestCase.test_method   # one test
python manage.py cleanup_portal_signups [--dry-run]     # delete expired pending patient signups (run daily)
npm install && npm run build:css                        # rebuild static/css/app.css after changing template classes (watch:css while editing)
```

Settings come from `.env` (see `.env.example`): `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` (comma-separated, defaults to localhost), `CSRF_TRUSTED_ORIGINS` (comma-separated full origins like `https://host`; empty by default), `DB_*` (MySQL), `STRIPE_*`, `SITE_URL` (public address used in email links; defaults to `http://127.0.0.1:8000`), optionally `EMAIL_BACKEND` (defaults to the console backend, so confirmation emails print to the runserver log) plus `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` for SMTP (other SMTP settings default to Gmail; the sender defaults to `EMAIL_HOST_USER`). There's no lint config.

**Database:** `DB_ENGINE=sqlite` in `.env` switches to SQLite (`BASE_DIR/db.sqlite3`); otherwise it's MySQL from `DB_*` (the local default). The code has no raw SQL or MySQL-only lookups, and the whole suite passes on both (`DB_ENGINE=sqlite python manage.py test`); keep it that way.

**Production** is PythonAnywhere's free tier with **SQLite**; `DEPLOY_PYTHONANYWHERE.md` has the exact steps. `requirements.txt` lists only what the app imports (the server doesn't need `mysqlclient`), and `requirements-local.txt` adds `mysqlclient` and `polib`. Static files are served by the Web tab mapping `/static/` → `staticfiles/` (run `collectstatic`), and the WSGI file just sets `DJANGO_SETTINGS_MODULE`, because settings load `.env` from `BASE_DIR`. When `DEBUG` is off, settings require `SECRET_KEY`, trust `X-Forwarded-Proto`, and use secure cookies (`SECURE_COOKIES`). `SECURE_SSL_REDIRECT` defaults off (PythonAnywhere's "Force HTTPS" does the redirect), and `SECURE_HSTS_SECONDS` defaults to 0. The MySQL connection sets `STRICT_TRANS_TABLES`.

Tests run against a temporary MySQL test database, so the DB user needs permission to create databases. Each app's `tests.py` builds on `tenants.testing.ClinicTestCase`, which sets up clinic `clinic-a` with an admin (`a@a.com`), a doctor (`d@a.com`) and a patient, plus helpers `login_as()`, `portal_login()`, `make_staff()`, `make_portal_patient()` and `expire_trial()`. `billing/tests.py` sends correctly signed Stripe webhooks, so webhook handlers can be tested without Stripe.

### Translations (Arabic)

```bash
python manage.py makemessages -l ar      # refresh locale/ar/LC_MESSAGES/django.po
python translate.py                      # fill msgstr from the dict in translate.py (needs polib, not in requirements.txt)
python manage.py compilemessages         # build django.mo
```

When you add a new `{% trans %}`/`gettext` string, add its Arabic translation to the `translations` dict in `translate.py`. That script also clears the `fuzzy` flag on entries it fills (compilemessages skips fuzzy entries). All app URLs sit under `i18n_patterns` with `prefix_default_language=True`, so every page URL starts with `/en/` or `/ar/`. Language switching goes through `/i18n/`.

## Architecture

### Multi-tenancy (shared DB, shared schema)
- `tenants.Clinic` (UUID PK, unique `slug`) is the tenant. Every tenant-owned model has a `clinic` FK.
- `tenants.middleware.CurrentClinicMiddleware` sets `request.clinic` from `session["clinic_id"]`, or `None` if that clinic is missing or inactive.
- **Tenant isolation depends on views filtering every query by `clinic=request.clinic`.** Use `get_object_or_404(Model, id=..., clinic=request.clinic)`, never a bare lookup by id.
- Context processors expose `current_clinic`, `staff_user` (`accounts.context_processors`, from `request.staff_user`) and `unread_notifications_count` to all templates, so views don't need to pass `staff_user` for the sidebar.

### Authentication (custom, not `django.contrib.auth`)
There are two separate session-based identities:
- **Staff**: `accounts.StaffUser` (bcrypt `password_hash`, roles `admin`/`doctor`/`reception`, email unique per clinic only). Staff log in with clinic slug + email + password; login sets both `clinic_id` and `staff_user_id` in the session (and calls `session.cycle_key()`, as all logins should). Guard staff views with `accounts.decorators.login_required_session` (sets `request.staff_user`, scoped to `request.clinic`) or `@role_required("admin", ...)`, which already includes the login check. A new clinic is created through `accounts` signup, and the admin account is activated by email confirmation (see below).

**Email confirmation** (`accounts/verification.py`, shared by staff signup and portal registration):
- Signup sends one email (HTML with a single "Yes, it's me / نعم، هذا أنا" button, plus a plain-text part). The link is built from `settings.SITE_URL`, never the request host. The token is a `TimestampSigner` token holding `{kind, id}` (`staff` → `StaffUser`, `portal` → `PortalSignup`). It's valid for 30 minutes and single-use because confirming changes state (the staff user becomes verified; the portal signup is consumed).
- `accounts:confirm_email` **GET only renders a page that auto-POSTs** (JavaScript, with a visible button as fallback). Mail scanners pre-open links with GET, so a GET must never confirm or log in. POST confirms, logs that browser in (`_log_in`) and redirects to the dashboard or portal dashboard. Expired, used or tampered tokens get `confirm_problem.html` (410/400) with a resend button when the account is still unconfirmed.
- Signup stores `session["pending_verification"]` and redirects to `accounts:check_email`, which polls `accounts:verification_status` every 3s and logs in once the account is confirmed on any device. Only the browser that signed up has that entry; never set it anywhere else (e.g. on the resend-by-email form), or someone could be logged in by another person confirming.
- Resending is limited to once per 60s per account through the cache (`send_confirmation_email` returns False when blocked). This uses LocMem by default, which is fine for PythonAnywhere's single worker.
- **Patient portal**: `patients.Patient` logs in at `/patients/portal/<clinic_slug>/login/`. The session holds `patient_id`. Registration writes only a `PortalSignup` row (with the password already hashed) and sends the confirmation email. Confirming calls `patients.utils.complete_portal_signup`, which creates the `Patient`, or attaches the login to a staff-created patient with the same email, and then deletes every pending signup for that email, so each link works once. Unconfirmed signups are kept 24h (`PENDING_SIGNUP_MAX_AGE`) so resend still works, then `cleanup_portal_signups` deletes them. Never write to `Patient` before the email is verified, or someone could take over a staff-created record just by knowing the patient's email. Guard portal views with `patients.decorators.login_required_patient` (sets `request.patient`, and its clinic is `request.patient.clinic`, not `request.clinic`).

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
- **Doctors** are `StaffUser`s with `role="doctor"`, created by an admin through `accounts:add_staff` (`?role=doctor` pre-selects the role). They log in through the same staff login. `accounts:doctors` lists them with today's and upcoming counts for all staff. `appointments:list?doctor=<id>` filters to one doctor (this is "My Appointments" in the doctor sidebar), and `appointments:book?doctor=<id>` pre-selects one. The dashboard shows doctors only their own appointments.
- `dashboard`: public landing page (`dashboard:landing`), clinic finder and account chooser, and the staff home (`dashboard:home`).

### Templates/static
- **Layouts:** `templates/base.html` is the staff shell: an off-canvas sidebar below `lg`, a top bar whose search submits `?q=` to `patients:list`, and toasts. `templates/public_base.html` is for the landing and auth pages, and `patients/templates/patients/portal_base.html` is for the patient portal. All three include `templates/includes/` (head with fonts/CSS/favicon, logo mark, language switch, toasts, confirm modal). Each app's pages are under `<app>/templates/<app>/`. A page marks its sidebar item active with `{% block nav_<name> %}nav-link-active{% endblock %}`.
- **CSS:** Tailwind 3.4 is **built**, not loaded from a CDN. The source is `static/src/input.css`, which defines the component classes (`btn-primary`/`btn-secondary`/`btn-ghost`/`btn-danger`, `input`, `label`, `card`, `badge-*`, `table` inside `table-wrap`, `page-header`/`page-title`, `stat-card`, `empty-state`, `nav-link`). The output is the committed `static/css/app.css`. After changing classes in templates, run `npm install` once, then `npm run build:css` (or `npm run watch:css`). Classes that aren't in a scanned file (`tailwind.config.js` `content`) are purged.
- **Template helpers** (`dashboard/templatetags/ui.py`, registered as a builtin, so no `{% load %}` is needed): `{% icon "name" "classes" %}` renders an inline Lucide SVG (add icons to `ICONS`; no emojis in the UI), `|status_badge` maps an appointment/billing status to a badge class, `|initials` gives avatar initials, and `|days_left` counts days until a datetime.
- **RTL:** use logical utilities (`ms-`/`me-`/`ps-`/`pe-`, `start-`/`end-`, `text-start`, `border-s`/`border-e`), never `ml`/`mr`/`left`/`right`. Arrows and chevrons get `rtl:rotate-180`. Phone numbers and emails get `dir="ltr"`.
- **JS** (`static/js/main.js`): sidebar toggle, auto-dismissing toasts, `<form data-confirm="Question?" data-confirm-button="Label">` opens the confirm modal before submitting, and every form's submit button is disabled and shows a spinner while it submits (opt out with `data-no-loading`).

## Known gotchas
- `TIME_ZONE` is `Asia/Hebron`. Use `timezone.localdate()`/`localtime()`, not `timezone.now().date()`.
- **Don't use `__date` lookups** (e.g. `scheduled_at__date=today`). On MySQL without loaded time zone tables they silently match nothing. Use `today_range()` with `__gte`/`__lt` instead.
- Views that change state (check-in, cancel, complete, mark read) are `@require_POST` and are triggered by small `<form method="post">` + `{% csrf_token %}` buttons, not `<a href>` links. Keep it that way.
- In templates, a filter argument that doesn't exist raises an error (`{{ a|default:missing.attr }}` crashes, unlike `{{ missing.attr }}`). Use `{% if %}` instead.