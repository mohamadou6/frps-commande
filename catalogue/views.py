from django.shortcuts import render

from accounts.decorators import formation_sanitaire_required

from .models import Magasin, Produit


@formation_sanitaire_required
def liste(request):
    query = request.GET.get("q", "").strip()
    produits = Produit.objects.filter(
        actif=True, magasin__in=[Magasin.PRINCIPAL, Magasin.UCPC]
    ).order_by("nom")
    if query:
        produits = produits.filter(nom__icontains=query)
    return render(request, "catalogue/liste.html", {"produits": produits, "query": query})
