# Deploying to PythonAnywhere (free tier)

The app runs at `https://yourusername.pythonanywhere.com` with PythonAnywhere's MySQL. Everything below happens on the PythonAnywhere website. Replace **`yourusername`** everywhere with your PythonAnywhere username.

**Free-tier limits that matter here**

- **One web app**, at `yourusername.pythonanywhere.com`. HTTPS is included.
- **It stops after 3 months** unless you click **"Run until 3 months from today"** on the Web tab. PythonAnywhere emails you before that happens.
- **Restricted internet access:** only an approved list of sites can be reached. Sending email through Gmail works, but reading the inbox (IMAP) doesn't, so **verification emails contain a link** instead of asking for a "YES" reply (`EMAIL_VERIFY_BY_REPLY=False` below). Stripe's API is on the approved list.
- **One scheduled task**, once a day.
- **Storage:** about 512 MB of disk space and a small MySQL database. Plenty to start.

---

## 1. Create the account

Sign up at https://www.pythonanywhere.com/pricing/ → **Create a Beginner account**. Your username becomes part of the web address, so choose it carefully.

## 2. Create the MySQL database

1. Open the **Databases** tab.
2. Under **MySQL password**, set a password and **write it down**. It's the app's database password.
3. Under **Create a database**, type `clinic_saas` and click **Create**. Its full name is `yourusername$clinic_saas`.
4. Note the **Database host address** shown at the top: `yourusername.mysql.pythonanywhere-services.com`.
5. Click the `yourusername$clinic_saas` database to open a MySQL console, and run this so Arabic text is stored correctly:

   ```sql
   ALTER DATABASE `yourusername$clinic_saas` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

   Then close that console tab.

## 3. Get the code and install the packages

Open the **Consoles** tab → **Bash**, and run:

```bash
git clone https://github.com/AhmadSHW/Clinic-Saas.git
cd Clinic-Saas
mkvirtualenv --python=/usr/bin/python3.13 clinic-env
pip install -r requirements.txt
```

- If `python3.13` isn't found, use `python3.12`; the project works on both.
- **Private repo?** `git clone` asks for a password. Use a GitHub *fine-grained personal access token* with read access to this repo, or make the repo public.
- The install takes a few minutes. In later consoles, run `workon clinic-env` first to use this environment again.

## 4. Create the `.env` file

Still in the console, generate a secret key and copy the output:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Then create the file with `nano .env`, paste the block below with your values filled in, save with **Ctrl+O, Enter**, and exit with **Ctrl+X**:

```ini
SECRET_KEY=paste-the-generated-key-here
DEBUG=False
ALLOWED_HOSTS=yourusername.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://yourusername.pythonanywhere.com

DB_NAME=yourusername$clinic_saas
DB_USER=yourusername
DB_PASSWORD='the-mysql-password-from-step-2'
DB_HOST=yourusername.mysql.pythonanywhere-services.com
DB_PORT=3306

# Gmail (App Password, no spaces). Verification emails carry a link on this host.
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST_USER=you@gmail.com
EMAIL_HOST_PASSWORD='your16charapppassword'
EMAIL_VERIFY_BY_REPLY=False

# Stripe (can be filled in later, see step 8)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
```

Keep the single quotes around the passwords. Then lock the file so only you can read it:

```bash
chmod 600 .env
```

## 5. Set up the database tables and static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

Optionally create a Django admin login with `python manage.py createsuperuser`.

If `migrate` fails with "Access denied", the password or username in `.env` doesn't match step 2.

## 6. Create the web app

1. Open the **Web** tab → **Add a new web app** → **Next**.
2. Choose **Manual configuration**, not the "Django" option, which would create a new empty project. Then pick **the same Python version** as in step 3 (3.13 or 3.12).
3. On the web app's page, fill in:

   | Section | Field | Value |
   |---|---|---|
   | Code | Source code | `/home/yourusername/Clinic-Saas` |
   | Code | Working directory | `/home/yourusername/Clinic-Saas` |
   | Virtualenv | Path | `/home/yourusername/.virtualenvs/clinic-env` |
   | Static files | URL `/static/` | Directory `/home/yourusername/Clinic-Saas/staticfiles` |
   | Security | Force HTTPS | **Enabled** |

4. In the **Code** section, click the **WSGI configuration file** link, `/var/www/yourusername_pythonanywhere_com_wsgi.py`. **Delete everything** in it, paste this, and click **Save**:

   ```python
   import os
   import sys

   path = "/home/yourusername/Clinic-Saas"
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

   The settings load `.env` from the project folder on their own.

5. Scroll to the top and click the green **Reload yourusername.pythonanywhere.com** button.

## 7. Open the site

Go to **https://yourusername.pythonanywhere.com**. You should see the landing page. Register your clinic; the verification email arrives with a link.

**Something wrong?** The **Web** tab has an **Error log** link. The last lines usually name the problem (see Troubleshooting below).

## 8. Stripe (when you're ready to take payments)

1. In the Stripe dashboard, go to **Developers → Webhooks → Add endpoint** with URL `https://yourusername.pythonanywhere.com/billing/webhook/` and these events: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted`.
2. Put the keys and the endpoint's signing secret into `.env`, then **Reload** the web app.
3. In Stripe's settings, save the **Customer portal** settings once, so "Manage payment method" works.

## 9. Daily cleanup task

Open the **Tasks** tab and add a daily task at any time, with this command:

```bash
/home/yourusername/.virtualenvs/clinic-env/bin/python /home/yourusername/Clinic-Saas/manage.py cleanup_portal_signups
```

It removes expired, unverified patient signups.

---

## Updating the site after you push new code

In a **Bash** console:

```bash
cd ~/Clinic-Saas
workon clinic-env
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload** on the **Web** tab.

## Backups

Free accounts have no automatic backups you control, so export the database now and then from a Bash console:

```bash
mysqldump -u yourusername -h yourusername.mysql.pythonanywhere-services.com --no-tablespaces 'yourusername$clinic_saas' | gzip > ~/backup-$(date +%F).sql.gz
```

Then download the file from the **Files** tab.

## Troubleshooting

| What you see | Likely cause |
|---|---|
| "Something went wrong :-(" page | Open the **Error log** on the Web tab and read the last error |
| `ImproperlyConfigured: SECRET_KEY must be set` | `.env` missing or in the wrong folder (it must be `/home/yourusername/Clinic-Saas/.env`) |
| `400 Bad Request` | `ALLOWED_HOSTS` doesn't match the address exactly |
| `403 CSRF verification failed` on forms | `CSRF_TRUSTED_ORIGINS` must be `https://yourusername.pythonanywhere.com` |
| Pages have no styling | The `/static/` mapping is wrong, or `collectstatic` wasn't run |
| `Access denied for user` | DB user/password in `.env` don't match the Databases tab |
| Arabic text shows as `???` | Step 2.5 (utf8mb4) was skipped before `migrate`. Run it, then recreate the tables |
| Emails don't arrive | Gmail App Password wrong or has spaces; check the error log |
| Site says it's disabled | Free web app expired. Web tab → **Run until 3 months from today** |
