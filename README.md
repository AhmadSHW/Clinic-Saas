# Clinic SaaS

A multi-tenant SaaS platform for managing small clinics and pharmacies — appointment booking, patient records, role-based staff access, and subscription billing.

## Features

- **Multi-tenancy**: each clinic operates as an independent, isolated tenant on a shared database
- **Role-based access control**: Admin, Doctor, and Reception roles with different permissions
- **Appointment booking & real-time waiting queue**: patients get a queue position on check-in
- **Patient records**: medical history tracked per visit
- **Subscription billing**: Stripe-powered monthly subscriptions with webhook-verified upgrades
- **Internal notification system**: staff get notified of new/cancelled appointments

## Tech Stack

- **Backend**: Django, MySQL
- **Frontend**: Bootstrap 5, vanilla JavaScript
- **Payments**: Stripe API
- **Auth**: Custom session-based authentication with bcrypt password hashing

## Setup

1. Clone the repository
2. Create a virtual environment and activate it
3. Install dependencies:
```bash
   pip install -r requirements.txt
```
4. Create a `.env` file (see `.env.example`)
5. Create the MySQL database
6. Run migrations:
```bash
   python manage.py migrate
```
7. Run the server:
```bash
   python manage.py runserver
```

## Architecture

Multi-tenancy is implemented using a shared database / shared schema approach — every model that belongs to a clinic has a `clinic` foreign key, and a custom middleware (`CurrentClinicMiddleware`) resolves the active clinic from the session on every request.