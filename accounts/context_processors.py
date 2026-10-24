def current_staff_user(request):
    """
    Exposes the logged-in staff member to every template, so the sidebar
    (role-based links, name/role footer) works on all staff pages and not
    only on views that pass staff_user themselves.
    request.staff_user is set by login_required_session. Public pages
    (landing, sign-in) don't use that decorator, so look the user up from
    the session there, letting the public header show "Go to dashboard".
    """
    staff_user = getattr(request, "staff_user", None)
    clinic = getattr(request, "clinic", None)
    staff_user_id = request.session.get("staff_user_id") if hasattr(request, "session") else None

    if staff_user is None and staff_user_id and clinic:
        from .models import StaffUser

        staff_user = StaffUser.objects.filter(
            id=staff_user_id, clinic=clinic, is_active=True
        ).first()

    return {"staff_user": staff_user}
