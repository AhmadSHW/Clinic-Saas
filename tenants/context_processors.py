def current_clinic(request):
    """




    """
    return {
        "current_clinic": getattr(request, "clinic", None),
    }