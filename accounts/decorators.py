# accounts/decorators.py
from functools import wraps
from django.shortcuts import redirect, render
from django.contrib import messages
from .models import StaffUser


def allow_expired_trial(view_func):
    """
    Marks a view as reachable after the clinic's trial ends (e.g. billing).
    Put it below @login_required_session / @role_required.
    """
    view_func.allow_expired_trial = True
    return view_func


def login_required_session(view_func):
    """
    Ensures the user is logged in within the current clinic, and blocks
    clinics whose trial has ended unless the view is @allow_expired_trial.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_id = request.session.get("staff_user_id")
        if not user_id:
            messages.error(request, "Please log in first.")
            return redirect("accounts:login")

        try:
            request.staff_user = StaffUser.objects.get(
                id=user_id, clinic=request.clinic, is_active=True
            )
        except StaffUser.DoesNotExist:
            request.session.pop("staff_user_id", None)
            messages.error(request, "Please log in first.")
            return redirect("accounts:login")

        if request.clinic.needs_subscription and not getattr(view_func, "allow_expired_trial", False):
            if request.staff_user.is_admin:
                messages.warning(request, "Your clinic doesn't have an active plan. Please subscribe to keep using Clinic SaS.")
                return redirect("billing:home")
            return render(request, "accounts/trial_expired.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    """
    Restricts a view to specific roles.
    Usage: @role_required("admin", "doctor")
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.staff_user.role not in allowed_roles:
                messages.error(request, "You don't have permission to access this page.")
                return redirect("dashboard:home")
            return view_func(request, *args, **kwargs)

        # Wrap after @wraps so login_required_session sees attributes like allow_expired_trial
        return login_required_session(wrapper)

    return decorator