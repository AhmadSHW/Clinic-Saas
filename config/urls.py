"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.templatetags.static import static
from django.views.generic import RedirectView
from billing.views import stripe_webhook

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    # Browsers ask for /favicon.ico on their own; point them at the SVG icon
    path("favicon.ico", RedirectView.as_view(url=static("favicon.svg"), permanent=True)),
    # Outside i18n_patterns: Stripe POSTs here, and a language redirect would drop the body
    path("billing/webhook/", stripe_webhook, name="stripe_webhook"),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("patients/", include("patients.urls")),
    path("appointments/", include("appointments.urls")),
    path("billing/", include("billing.urls")),
    path("notifications/", include("notifications.urls")),
    path("", include("dashboard.urls")),
    prefix_default_language=True,
)