function normaliserTexte(texte) {
    return texte.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function initCombobox({ inputId, hiddenId, listId, data }) {
    const input = document.getElementById(inputId);
    const hidden = document.getElementById(hiddenId);
    const liste = document.getElementById(listId);
    if (!input || !hidden || !liste) return;

    const donnees = data.map((item) => ({ ...item, nomNormalise: normaliserTexte(item.nom) }));

    function afficherSuggestions(items) {
        liste.innerHTML = "";
        if (!items.length) {
            liste.style.display = "none";
            return;
        }
        items.forEach((item) => {
            const bouton = document.createElement("button");
            bouton.type = "button";
            bouton.className = "list-group-item list-group-item-action";
            bouton.textContent = item.nom;
            bouton.addEventListener("click", () => {
                input.value = item.nom;
                hidden.value = item.id;
                liste.innerHTML = "";
                liste.style.display = "none";
            });
            liste.appendChild(bouton);
        });
        liste.style.display = "block";
    }

    input.addEventListener("input", () => {
        hidden.value = "";
        const requete = normaliserTexte(input.value.trim());
        const resultats = requete ? donnees.filter((item) => item.nomNormalise.includes(requete)) : donnees;
        afficherSuggestions(resultats);
    });

    input.addEventListener("focus", () => {
        input.dispatchEvent(new Event("input"));
    });

    document.addEventListener("click", (evenement) => {
        if (!liste.contains(evenement.target) && evenement.target !== input) {
            liste.style.display = "none";
        }
    });
}
