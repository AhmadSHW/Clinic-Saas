# Clinic SaaS

A multi-tenant SaaS platform for managing small clinics and pharmacies — appointment booking, patient records, a self-service patient portal, role-based staff access, and subscription billing. Available in English and Arabic.

## Features

- **Multi-tenancy**: each clinic operates as an independent, isolated tenant on a shared database
- **Role-based access control**: Admin, Doctor, and Reception roles with different permissions — only doctors and admins can add medical records
- **Appointment booking & waiting queue**: patients get a ticket-style queue number on check-in that never repeats within the day
- **Patient records**: medical history tracked per visit
- **Patient portal**: patients find their clinic, register, book and cancel their own appointments
  - Email verification is required before an account is created, so a patient record added by staff can't be claimed by someone who only knows the patient's email
- **Subscription billing (Stripe)**: a $49/month Pro plan
  - Upgrades are confirmed by webhook
  - Failed payments are marked past due and admins are alerted
  - Renewals are recorded
  - Admins can update their card through Stripe's billing portal
- **14-day free trial**: when the trial — or a paid subscription — ends, staff are locked out and admins are sent to the billing page; the clinic's patient portal closes until it subscribes
- **Internal notification system**: staff get notified of new/cancelled appointments and billing problems
- **English & Arabic**: every page is available in both languages (`/en/...` and `/ar/...`)

## Tech Stack

- **Backend**: Django 5.2, MySQL
- **Frontend**: Django templates, Tailwind CSS 3 (built with npm, output committed), vanilla JavaScript, Lucide icons, Inter and IBM Plex Sans Arabic fonts. Responsive on phones and fully right-to-left in Arabic
- **Payments**: Stripe API (Checkout, webhooks, billing portal)
- **Auth**: Custom session-based authentication with bcrypt password hashing and signed email-verification links

## Setup

1. Clone the repository
2. Create a virtual environment and activate it
3. Install dependencies:
```bash
   pip install -r requirements.txt
```
4. Create a `.env` file from `.env.example`:

   | Variable | Purpose |
   |---|---|
   | `SECRET_KEY` | Django secret key (required) |
   | `DEBUG` | `True` for development; anything else is off |
   | `ALLOWED_HOSTS` | Comma-separated hostnames (default `localhost,127.0.0.1`) |
   | `CSRF_TRUSTED_ORIGINS` | Comma-separated origins with scheme, e.g. `https://clinic.example.com` (needed in production behind HTTPS) |
   | `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL connection |
   | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe keys |
   | `EMAIL_BACKEND` | Optional; defaults to printing emails to the console. Set to `django.core.mail.backends.smtp.EmailBackend` to really send |
   | `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP login. For Gmail use your address and a [Google App Password](https://myaccount.google.com/apppasswords) |
   | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_IMAP_HOST`, `DEFAULT_FROM_EMAIL` | Optional; default to Gmail (`smtp.gmail.com`, 587, TLS, `imap.gmail.com`) and the login address |

5. Create the MySQL database
6. Run migrations:
```bash
   python manage.py migrate
```
7. Run the server:
```bash
   python manage.py runserver
```

**Email verification:** with Gmail configured (SMTP backend plus `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`), the verification email has no link. The user just replies **YES** (or نعم). The app reads the replies from the same Gmail inbox over IMAP, using the same App Password, and the "check your email" page signs the user in as soon as the reply arrives. Without SMTP configured, emails are printed to the runserver console with a verification link instead.

### Signing in

- **Clinic staff**: register a clinic at `/en/accounts/signup/`, verify the email, then sign in with the clinic URL (its slug), email, and password.
- **Patients**: choose "Patient" on the account chooser and use "Find Your Clinic", then register or log in on that clinic's portal.

## Stripe

1. Create a webhook endpoint pointing at `https://<your-domain>/billing/webhook/` (no language prefix) with these events:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.deleted`
2. Put its signing secret in `STRIPE_WEBHOOK_SECRET`.
3. In the Stripe dashboard, save the **Customer portal** settings once (needed for "Manage payment method"), and under subscription settings choose to **cancel the subscription** when all payment retries fail.

For local testing:
```bash
stripe listen --forward-to localhost:8000/billing/webhook/
```

## Deployment

See **[PYTHONANYWHERE.md](PYTHONANYWHERE.md)** for step-by-step instructions to run it on PythonAnywhere's free tier with its MySQL database.

## Tests

```bash
python manage.py test                 # all apps
python manage.py test billing         # one app
```

Tests use a temporary MySQL database, so the database user needs permission to create databases.

## Maintenance

Delete pending patient signups whose verification link has expired (run daily, e.g. with cron or Task Scheduler):
```bash
python manage.py cleanup_portal_signups            # add --dry-run to preview
```

Activate accounts that replied YES but never came back to the site (optional; the site also checks on its own while someone waits or logs in):
```bash
python manage.py check_verification_replies
```

## Frontend (CSS)

The stylesheet `static/css/app.css` is built by Tailwind from `static/src/input.css` and is committed, so running the app doesn't need Node. If you change classes in a template, rebuild it (requires Node.js):

```bash
npm install           # once
npm run build:css     # or: npm run watch:css while editing
```

## Translations

```bash
python manage.py makemessages -l ar
python translate.py                  # fills Arabic strings from the dictionary in translate.py (requires polib)
python manage.py compilemessages
```

## Architecture

Multi-tenancy is implemented using a shared database / shared schema approach — every model that belongs to a clinic has a `clinic` foreign key, and a custom middleware (`CurrentClinicMiddleware`) resolves the active clinic from the session on every request.

Staff and patients have separate sessions and separate login decorators (`login_required_session` / `role_required` for staff, `login_required_patient` for the portal). The staff decorators also enforce the trial/subscription lockout. Views that change data accept only POST requests with a CSRF token.

Billing state is driven entirely by Stripe webhooks — the checkout success page never upgrades a clinic on its own, since anyone could visit it without paying.
