# Deploying to PythonAnywhere (free tier, SQLite)

- **Account:** `AboShwiki`
- **Site:** https://aboshwiki.pythonanywhere.com
- **Project folder on the server:** `/home/AboShwiki/Clinic-Saas`
- **Database:** SQLite, a `db.sqlite3` file in the project folder (`DB_ENGINE=sqlite` in `.env`). Your local machine keeps using MySQL.
- **Python:** the project runs on **3.14** locally. On PythonAnywhere, use **3.13** (or 3.12 if 3.13 isn't offered); all the packages support both.

Run every command below in a PythonAnywhere **Bash console** (**Consoles** tab → **Bash**).

---

## 1. Get the code

```bash
cd ~
git clone https://github.com/AhmadSHW/Clinic-Saas.git
```

This creates `/home/AboShwiki/Clinic-Saas`.

**If the repo is private:** `git clone` asks for a username and password. Enter your GitHub username, and as the password a **fine-grained personal access token**: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate. Give it access to `Clinic-Saas` only, with **Contents: Read-only**. Your normal GitHub password won't work.

## 2. Create the virtualenv and install the packages

```bash
mkvirtualenv --python=/usr/bin/python3.13 clinic-env
cd ~/Clinic-Saas
pip install -r requirements.txt
```

- If `python3.13` isn't found, use `/usr/bin/python3.12` instead (and pick the same version in step 6).
- `requirements.txt` holds only what the server needs: about 13 small packages, no MySQL driver.
- In any **new** console later, run `workon clinic-env` first to switch back to this environment.

## 3. Create the `.env` file

Generate a secret key and copy the output:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Open the editor:

```bash
nano ~/Clinic-Saas/.env
```

Paste this, put the generated key after `SECRET_KEY=`, and save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**:

```ini
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=aboshwiki.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://aboshwiki.pythonanywhere.com
# Used to build the button link in confirmation emails
SITE_URL=https://aboshwiki.pythonanywhere.com

DB_ENGINE=sqlite

# Email. As written, emails (including confirmation emails) are printed to the
# "Server log" on the Web tab instead of being sent. To send real emails through
# Gmail, uncomment the next three lines and fill in your address and App Password.
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST_USER=
# EMAIL_HOST_PASSWORD=

# Stripe (fill in when you set up payments)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
```

If a password contains `$` or spaces, put it in single quotes, e.g. `EMAIL_HOST_PASSWORD='abcd...'`.

Make the file readable only by you:

```bash
chmod 600 ~/Clinic-Saas/.env
```

## 4. Create the database, collect static files, create an admin

```bash
cd ~/Clinic-Saas
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

- `migrate` creates `db.sqlite3` with all the tables.
- `collectstatic` copies the CSS, JavaScript and icons into `staticfiles/`.
- `createsuperuser` asks for a username, email and password for the Django admin at `/admin/`. This is optional; clinic accounts are created through the site's own sign-up.

## 5. Create the web app

1. Open the **Web** tab → **Add a new web app** → **Next**.
2. Choose **Manual configuration**. **Not** "Django": that option creates a new empty project.
3. Choose **Python 3.13**, the same version as the virtualenv. Click **Next**.

## 6. Configure the web app

On the web app's page (Web tab), fill in:

| Section | Field | Value |
|---|---|---|
| **Code** | Source code | `/home/AboShwiki/Clinic-Saas` |
| **Code** | Working directory | `/home/AboShwiki/Clinic-Saas` |
| **Virtualenv** | Enter path to a virtualenv | `/home/AboShwiki/.virtualenvs/clinic-env` |
| **Static files** | URL | `/static/` |
| **Static files** | Directory | `/home/AboShwiki/Clinic-Saas/staticfiles` |
| **Security** | Force HTTPS | **Enabled** |

## 7. Edit the WSGI file

In the **Code** section, click the link **`/var/www/aboshwiki_pythonanywhere_com_wsgi.py`**. **Delete everything** in that file, paste the following, and click **Save**:

```python
# /var/www/aboshwiki_pythonanywhere_com_wsgi.py
import os
import sys

# Make the project importable
path = "/home/AboShwiki/Clinic-Saas"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

# config/settings.py loads /home/AboShwiki/Clinic-Saas/.env itself, by full path,
# so nothing else is needed here.
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

## 8. Start it

At the top of the **Web** tab, click the green **Reload aboshwiki.pythonanywhere.com** button, then open:

**https://aboshwiki.pythonanywhere.com**

You should see the landing page, styled and in colour. Register your clinic. With Gmail configured, you get an email with a green **Yes, it's me** button: press it (on any device) and you're signed in. With the default `.env` above, the email is printed to the **Server log** on the Web tab instead.

**If something's wrong:** the Web tab has an **Error log** link. The last lines name the problem (see Troubleshooting).

---

## Updating the site later

After you push new code to GitHub, run this in a Bash console:

```bash
workon clinic-env
cd ~/Clinic-Saas
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload aboshwiki.pythonanywhere.com** on the Web tab.

`git pull` never touches `.env` or `db.sqlite3`: both are in `.gitignore`, so your settings and data stay as they are.

## Backing up the database

The whole database is the single file `db.sqlite3`. To make a dated copy (this only copies; it deletes nothing):

```bash
cp ~/Clinic-Saas/db.sqlite3 ~/db-backup-$(date +%F).sqlite3
```

Download copies now and then from the **Files** tab, since the server is the only place they exist.

## Things to know about the free tier

- **Renewal:** the site stops after **3 months** unless you click **"Run until 3 months from today"** on the Web tab. PythonAnywhere emails a reminder first.
- **Disk:** 512 MB. The installed packages take roughly 60 MB, so there's plenty of room.
- **Outbound internet** is limited to an approved list of sites. Gmail sending works, and Stripe's API is on the list.
- **Stripe webhook** (when you add payments): `https://aboshwiki.pythonanywhere.com/billing/webhook/`, with the four events listed in the README.
- **Daily cleanup (optional):** on the **Tasks** tab, add a daily task with this command:
  `/home/AboShwiki/.virtualenvs/clinic-env/bin/python /home/AboShwiki/Clinic-Saas/manage.py cleanup_portal_signups`

## Troubleshooting

| What you see | Likely cause |
|---|---|
| "Something went wrong :-(" | Open the **Error log** on the Web tab and read the last error |
| `ImproperlyConfigured: SECRET_KEY must be set` | `.env` is missing, empty, or not in `/home/AboShwiki/Clinic-Saas/` |
| `ModuleNotFoundError: No module named 'django'` | Virtualenv path on the Web tab is wrong, or step 2 wasn't run |
| `400 Bad Request` | `ALLOWED_HOSTS` must be exactly `aboshwiki.pythonanywhere.com` |
| `403 CSRF verification failed` on forms | `CSRF_TRUSTED_ORIGINS` must be exactly `https://aboshwiki.pythonanywhere.com` |
| Page has no styling | Static files mapping (step 6) is wrong, or `collectstatic` wasn't run |
| `no such table: ...` | `python manage.py migrate` wasn't run (step 4) |
| `attempt to write a readonly database` | Run `chmod 664 ~/Clinic-Saas/db.sqlite3`, then Reload |
| Site says it's disabled | Free web app expired. Click **Run until 3 months from today** |
