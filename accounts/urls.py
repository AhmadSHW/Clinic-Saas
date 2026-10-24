# accounts/urls.py
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.clinic_signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/add/", views.add_staff, name="add_staff"),
    path("doctors/", views.doctor_list, name="doctors"),
    path("settings/", views.clinic_settings, name="settings"),
    path("verification-status/", views.verification_status, name="verification_status"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("resend-verification/", views.resend_verification, name="resend_verification"),

]