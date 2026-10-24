# patients/urls.py
from django.urls import path
from . import views

app_name = "patients"

urlpatterns = [
    path("", views.patient_list, name="list"),
    path("add/", views.add_patient, name="add"),
    path("<int:patient_id>/", views.patient_detail, name="detail"),

    # Patient portal — self-service, separate from staff accounts
    path("portal/<slug:clinic_slug>/register/", views.portal_register, name="portal_register"),
    path("portal/<slug:clinic_slug>/login/", views.portal_login, name="portal_login"),
    path("portal/logout/", views.portal_logout, name="portal_logout"),
    path("portal/dashboard/", views.portal_dashboard, name="portal_dashboard"),
    path("portal/book/", views.portal_book_appointment, name="portal_book"),
    path("portal/appointments/<int:appointment_id>/cancel/", views.portal_cancel_appointment, name="portal_cancel"),
]