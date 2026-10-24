def current_staff_user(request):
    """
    Exposes the logged-in staff member to every template, so the sidebar
    (role-based links, name/role footer) works on all staff pages and not
    only on views that pass staff_user themselves.
    request.staff_user is set by login_required_session.
    """
    return {
        "staff_user": getattr(request, "staff_user", None),
    }
