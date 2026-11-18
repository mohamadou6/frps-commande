from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import _deconnecter_fosa_sans_fiche, formation_sanitaire_only_required
from commandes.models import Commande, StatutCommande
from notifications.models import DestinataireEmail

from . import services
from .models import MotifReclamation, PhotoReclamation, Reclamation, StatutReclamation


def _reclamations_visibles(request):
    """La FOSA ne voit que les siennes ; le personnel FRPS les voit toutes."""
    user = request.user
    if user.is_formation_sanitaire:
        return Reclamation.objects.filter(formation_sanitaire=user.formation_sanitaire)
    return Reclamation.objects.all()


def _compte_valide(view_func):
    """Connecté, et pas un compte FOSA sans fiche (il ferait planter les requêtes)."""

    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.est_fosa_sans_fiche:
            return _deconnecter_fosa_sans_fiche(request)
        return view_func(request, *args, **kwargs)

    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@_compte_valide
def liste(request):
    reclamations = _reclamations_visibles(request).select_related("formation_sanitaire", "commande")
    filtre = request.GET.get("statut", "")
    query = request.GET.get("q", "").strip()
    est_fosa = request.user.is_formation_sanitaire

    if not est_fosa:
        if filtre == "a_traiter" or not filtre:
            filtre = "a_traiter"
            reclamations = reclamations.exclude(statut=StatutReclamation.RESOLUE)
        elif filtre in StatutReclamation.values:
            reclamations = reclamations.filter(statut=filtre)
        else:
            filtre = "toutes"
        if query:
            reclamations = reclamations.filter(formation_sanitaire__nom__icontains=query)

    toutes = _reclamations_visibles(request)
    filtres = [
        ("a_traiter", "À traiter", toutes.exclude(statut=StatutReclamation.RESOLUE).count()),
        *[(code, libelle, toutes.filter(statut=code).count()) for code, libelle in StatutReclamation.choices],
        ("toutes", "Toutes", None),
    ]
    return render(
        request,
        "reclamations/liste.html",
        {
            "reclamations": reclamations[:300],
            "filtre": filtre,
            "filtres": filtres,
            "query": query,
            # Rappel à l'admin : sans adresse paramétrée, aucune réclamation ne part par e-mail.
            "sans_destinataire_email": request.user.is_admin_frps
            and not DestinataireEmail.objects.pour("recoit_reclamations").exists(),
        },
    )


@formation_sanitaire_only_required
def nouvelle(request):
    fosa = request.user.formation_sanitaire
    commandes = (
        Commande.objects.filter(formation_sanitaire=fosa)
        .exclude(statut__in=[StatutCommande.BROUILLON, StatutCommande.EN_ATTENTE_SYNCHRO])
        .order_by("-date_creation")[:50]
    )
    valeurs = {
        "motif": request.POST.get("motif", ""),
        "description": request.POST.get("description", ""),
        "commande": request.POST.get("commande", request.GET.get("commande", "")),
    }

    if request.method == "POST":
        commande = None
        if valeurs["commande"]:
            commande = Commande.objects.filter(pk=valeurs["commande"], formation_sanitaire=fosa).first()
            if commande is None:
                messages.error(request, "Commande introuvable.")
        if valeurs["commande"] == "" or commande is not None:
            try:
                reclamation = services.creer_reclamation(
                    fosa,
                    request.user,
                    valeurs["motif"],
                    valeurs["description"],
                    commande=commande,
                    photos=request.FILES.getlist("photos"),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request, f"Réclamation #{reclamation.pk} envoyée. Le FRPS vous répondra ici."
                )
                return redirect("reclamations:detail", reclamation_id=reclamation.pk)

    return render(
        request,
        "reclamations/nouvelle.html",
        {
            "commandes": commandes,
            "motifs": MotifReclamation.choices,
            "valeurs": valeurs,
            "photos_max": services.PHOTOS_MAX_PAR_ENVOI,
        },
    )


@_compte_valide
def detail(request, reclamation_id):
    reclamation = get_object_or_404(
        _reclamations_visibles(request).select_related("formation_sanitaire", "commande", "traitee_par"),
        pk=reclamation_id,
    )
    services.marquer_lue(reclamation, par_la_fosa=request.user.is_formation_sanitaire)
    return render(
        request,
        "reclamations/detail.html",
        {
            "reclamation": reclamation,
            "fil": reclamation.messages.select_related("auteur").prefetch_related(
                # Sans `only`, la page chargerait les octets de chaque photo pour rien.
                Prefetch("photos", queryset=PhotoReclamation.objects.only("pk", "message_id", "largeur", "hauteur"))
            ),
            "photos_initiales": reclamation.photos.filter(message__isnull=True).only("pk", "largeur", "hauteur"),
            "statuts": StatutReclamation.choices,
            "photos_max": services.PHOTOS_MAX_PAR_ENVOI,
        },
    )


@_compte_valide
@require_POST
def repondre(request, reclamation_id):
    reclamation = get_object_or_404(_reclamations_visibles(request), pk=reclamation_id)
    texte = request.POST.get("texte", "")
    photos = request.FILES.getlist("photos")
    try:
        if request.user.is_formation_sanitaire:
            reclamation = services.message_fosa(reclamation, request.user, texte, photos=photos)
            messages.success(request, "Message envoyé au FRPS.")
        elif request.user.role in ("admin", "personnel_stock", "personnel_comptabilite"):
            reclamation = services.reponse_frps(
                reclamation, request.user, texte, statut=request.POST.get("statut") or None, photos=photos
            )
            messages.success(request, "Réclamation mise à jour.")
        else:
            raise PermissionDenied
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("reclamations:detail", reclamation_id=reclamation.pk)


@_compte_valide
def photo(request, photo_id):
    """Sert une photo jointe, avec les mêmes droits que la réclamation : la FOSA ne
    voit que les siennes. Jamais de cache partagé : `private`."""
    photo = get_object_or_404(PhotoReclamation, pk=photo_id, reclamation__in=_reclamations_visibles(request))
    reponse = HttpResponse(bytes(photo.contenu), content_type="image/jpeg")
    reponse["Cache-Control"] = "private, max-age=86400"
    reponse["Content-Disposition"] = f'inline; filename="reclamation_{photo.reclamation_id}_photo_{photo.pk}.jpg"'
    return reponse
