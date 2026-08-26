from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone


class ActiviteMiddleware:
    """Met à jour derniere_activite à chaque requête authentifiée (max 1 écriture/5 min)."""

    INTERVALLE = 300  # secondes

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            maintenant = timezone.now()
            dernier = request.user.derniere_activite
            if dernier is None or (maintenant - dernier).total_seconds() > self.INTERVALLE:
                get_user_model().objects.filter(pk=request.user.pk).update(derniere_activite=maintenant)
        return response


class Custom404Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404:
            return render(request, "404.html", status=404)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            return render(request, "404.html", status=404)
        return None
