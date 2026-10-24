# dashboard/urls.py
from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.home, name="home"),
    path("accounts-choice/", views.account_chooser, name="account_chooser"),
    path("find-clinic/", views.find_clinic, name="find_clinic"),
]