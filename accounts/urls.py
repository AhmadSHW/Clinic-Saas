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
    # Email confirmation (accounts/verification.py)
    path("check-email/", views.check_email, name="check_email"),
    path("check-email/status/", views.verification_status, name="verification_status"),
    path("check-email/resend/", views.resend_pending, name="resend_pending"),
    path("confirm/<str:token>/", views.confirm_email, name="confirm_email"),
    path("confirm/<str:token>/resend/", views.resend_from_token, name="resend_from_token"),
    path("resend-verification/", views.resend_verification, name="resend_verification"),

]