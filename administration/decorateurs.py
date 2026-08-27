from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def admin_requis(vue):
    @login_required
    @wraps(vue)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.profil == "DG"):
            raise PermissionDenied
        return vue(request, *args, **kwargs)
    return wrapper
