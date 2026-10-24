# billing/urls.py
from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("", views.billing_home, name="home"),
    path("subscribe/", views.create_checkout_session, name="subscribe"),
    path("success/", views.checkout_success, name="success"),
    path("payment-method/", views.billing_portal, name="portal"),
]