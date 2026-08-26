from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification, Profil, TYPES_NOTIFICATION_STOCK


def page_404(request, exception=None):
    return render(request, "404.html", status=404)


@login_required
def deconnexion(request):
    auth_logout(request)
    return redirect("connexion")


def _qs_notifs(user):
    if user.is_superuser:
        return Notification.objects.none()
    qs = Notification.objects.filter(destinataire=user, lue=False)
    if user.profil == Profil.COMMERCIAL:
        qs = qs.exclude(type__in=TYPES_NOTIFICATION_STOCK)
    return qs


@login_required
def notifications_liste(request):
    notifs = _qs_notifs(request.user).order_by("-cree_le")[:60]
    return render(request, "core/notifications.html", {"notifs": notifs})


@login_required
def notifications_count(request):
    return JsonResponse({"nb": _qs_notifs(request.user).count()})


@login_required
@require_POST
def notification_marquer_lue(request, pk):
    notif = get_object_or_404(Notification, pk=pk, destinataire=request.user)
    notif.lue = True
    notif.save(update_fields=["lue"])
    if notif.groupe:
        Notification.objects.filter(groupe=notif.groupe, lue=False).update(lue=True)
    return redirect(notif.lien or "notifications_liste")
