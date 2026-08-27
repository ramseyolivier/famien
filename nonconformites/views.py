import io
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import Profil, TypeNotification, Utilisateur
from core.services import creer_notification

from .models import NonConformite, StatutNonConformite, TypeNonConformite
from .services import ajouter_action, annuler_nc, cloturer_nc, creer_nc


def _qs_visible(user):
    """QuerySet des NCs que cet utilisateur a le droit de consulter."""
    if user.acces_national or user.is_superuser:
        return NonConformite.objects.all()
    return NonConformite.objects.filter(cree_par=user)


@login_required
def nc_liste(request):
    qs = (
        _qs_visible(request.user)
        .select_related("site", "cree_par")
        .order_by("-cree_le")
    )
    statut_filtre = request.GET.get("statut", "")
    type_filtre = request.GET.get("type", "")
    if statut_filtre:
        qs = qs.filter(statut=statut_filtre)
    if type_filtre:
        qs = qs.filter(type=type_filtre)
    sites_filtre = (
        _qs_visible(request.user)
        .exclude(site=None)
        .values("site_id", "site__nom")
        .distinct()
        .order_by("site__nom")
    )

    return render(request, "nonconformites/liste.html", {
        "ncs": qs[:200],
        "statuts": StatutNonConformite.choices,
        "types": TypeNonConformite.choices,
        "sites_filtre": sites_filtre,
    })


@login_required
def nc_formulaire(request):
    if request.method == "POST":
        type_nc = request.POST.get("type", "")
        titre = request.POST.get("titre", "").strip()
        description = request.POST.get("description", "").strip()
        reference = request.POST.get("reference_document", "").strip()

        if not type_nc:
            messages.error(request, "Le type est obligatoire.")
        elif not titre:
            messages.error(request, "Le titre est obligatoire.")
        elif not description:
            messages.error(request, "La description est obligatoire.")
        else:
            try:
                nc = creer_nc(
                    auteur=request.user,
                    type_nc=type_nc,
                    titre=titre,
                    description=description,
                    reference=reference,
                    image=request.FILES.get("image") or None,
                )
                messages.success(request, "Non-conformité enregistrée.")
                return redirect("nc_detail", pk=nc.pk)
            except Exception as e:
                messages.error(request, str(e))

    return render(request, "nonconformites/formulaire.html", {
        "types": TypeNonConformite.choices,
        "user_site": request.user.site,
    })


@login_required
def nc_detail(request, pk):
    nc = get_object_or_404(
        _qs_visible(request.user)
        .select_related("site", "cree_par", "cloture_par")
        .prefetch_related("actions__cree_par"),
        pk=pk,
    )
    peut_cloturer = (
        request.user.profil == Profil.DG
        or request.user.is_superuser
    )
    peut_supprimer = peut_cloturer
    peut_relancer = peut_cloturer

    # Utilisateurs sur le même site ou dans l'équipe (pour la relance)
    if nc.site:
        utilisateurs_zone = (
            Utilisateur.objects.filter(site=nc.site)
            .exclude(pk=request.user.pk)
            .order_by("first_name", "last_name", "username")
        )
    else:
        utilisateurs_zone = (
            Utilisateur.objects.exclude(pk=request.user.pk)
            .order_by("first_name", "last_name", "username")
        )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "ajouter_action":
            desc = request.POST.get("description", "").strip()
            if not desc:
                messages.error(request, "La description de l'action est obligatoire.")
            else:
                try:
                    ajouter_action(nc, par=request.user, description=desc)
                    messages.success(request, "Action corrective ajoutée.")
                except ValidationError as e:
                    messages.error(request, str(e))
        elif action == "cloturer" and peut_cloturer:
            try:
                cloturer_nc(nc, par=request.user)
                messages.success(request, "Non-conformité clôturée.")
            except ValidationError as e:
                messages.error(request, str(e))
        elif action == "annuler" and peut_cloturer:
            try:
                annuler_nc(nc, par=request.user)
                messages.success(request, "Non-conformité annulée.")
            except ValidationError as e:
                messages.error(request, str(e))
        elif action == "relancer" and peut_relancer:
            dest_id = request.POST.get("destinataire")
            try:
                dest = utilisateurs_zone.get(pk=dest_id)
                nom_expediteur = request.user.get_full_name() or request.user.username
                creer_notification(
                    dest,
                    type=TypeNotification.NON_CONFORMITE,
                    titre=f"Relance — NC #{nc.pk} : {nc.titre}",
                    message=f"Relancé par {nom_expediteur}. Merci de traiter cette non-conformité.",
                    lien=f"/nonconformites/{nc.pk}/",
                )
                messages.success(request, f"Relance envoyée à {dest.get_full_name() or dest.username}.")
            except Utilisateur.DoesNotExist:
                messages.error(request, "Destinataire non valide.")
        return redirect("nc_detail", pk=pk)

    return render(request, "nonconformites/detail.html", {
        "nc": nc,
        "peut_cloturer": peut_cloturer,
        "peut_supprimer": peut_supprimer,
        "peut_relancer": peut_relancer,
        "utilisateurs_zone": utilisateurs_zone if peut_relancer else [],
    })


@login_required
def nc_exporter_word(request, pk):
    nc = get_object_or_404(
        _qs_visible(request.user).prefetch_related("actions__cree_par"),
        pk=pk,
    )
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    doc.core_properties.title = f"Non-conformité #{nc.pk}"

    titre = doc.add_heading(f"Non-conformité #{nc.pk} — {nc.titre}", level=1)
    titre.runs[0].font.color.rgb = RGBColor(0xDC, 0x26, 0x26)

    meta = doc.add_paragraph()
    meta.add_run("Type : ").bold = True
    meta.add_run(nc.get_type_display())
    meta.add_run("    Statut : ").bold = True
    meta.add_run(nc.get_statut_display())
    if nc.site:
        meta.add_run("    Site : ").bold = True
        meta.add_run(nc.site.nom)

    meta2 = doc.add_paragraph()
    meta2.add_run("Déclarée le : ").bold = True
    meta2.add_run(nc.cree_le.strftime("%d/%m/%Y à %H:%M"))
    meta2.add_run("    par : ").bold = True
    meta2.add_run(nc.cree_par.get_full_name() or nc.cree_par.username)
    if nc.reference_document:
        meta2.add_run(f"    Réf. : {nc.reference_document}")

    doc.add_heading("Description", level=2)
    doc.add_paragraph(nc.description)

    if nc.image and nc.image.name:
        try:
            img_path = nc.image.path
            if os.path.exists(img_path):
                doc.add_heading("Photo jointe", level=2)
                doc.add_picture(img_path, width=Inches(5))
        except Exception:
            pass

    if nc.actions.exists():
        doc.add_heading("Actions correctives / Explications", level=2)
        for action in nc.actions.all():
            p = doc.add_paragraph(style="List Bullet")
            auteur = action.cree_par.get_full_name() or action.cree_par.username
            p.add_run(f"{auteur} — {action.cree_le.strftime('%d/%m/%Y %H:%M')} : ").bold = True
            p.add_run(action.description)

    if nc.cloture_le:
        doc.add_paragraph()
        p = doc.add_paragraph()
        p.add_run("Clôturée le : ").bold = True
        cloture_par = nc.cloture_par.get_full_name() or nc.cloture_par.username if nc.cloture_par else "—"
        p.add_run(f"{nc.cloture_le.strftime('%d/%m/%Y à %H:%M')} par {cloture_par}")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    nom_fichier = f"NC_{nc.pk}_{nc.titre[:40].replace(' ', '_')}.docx"
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
    return response


@login_required
def nc_supprimer(request, pk):
    if request.user.profil != Profil.DG and not request.user.is_superuser:
        messages.error(request, "Accès refusé.")
        return redirect("nc_liste")
    nc = get_object_or_404(NonConformite, pk=pk)
    if request.method == "POST":
        nc.delete()
        messages.success(request, "Non-conformité supprimée.")
        return redirect("nc_liste")
    return redirect("nc_detail", pk=pk)
