from .models import Notification, Profil, TYPES_NOTIFICATION_STOCK


def notifications(request):
    if not request.user.is_authenticated:
        return {"nb_notifs": 0}
    qs = Notification.objects.filter(destinataire=request.user, lue=False)
    if False:
        qs = qs.exclude(type__in=TYPES_NOTIFICATION_STOCK)
    return {"nb_notifs": qs.count()}
