/*
  Filtrage des tableaux.
  - initFiltre()   : filtrage côté client (admin, sans rechargement).
  - autoFiltrer()  : soumet automatiquement le formulaire serveur dès qu'un
                     champ change (selects, dates, cases à cocher).
*/

function autoFiltrer(formSelector) {
  const form = typeof formSelector === 'string'
    ? document.querySelector(formSelector)
    : formSelector;
  if (!form) return;
  form.querySelectorAll('select, input[type="date"], input[type="checkbox"]').forEach(function(el) {
    el.addEventListener('change', function() { form.submit(); });
  });
}
function initFiltre({ tableId, inputId, selects = [] }) {
  const input   = document.getElementById(inputId);
  const table   = document.getElementById(tableId);
  if (!input || !table) return;

  const tbody   = table.querySelector('tbody');
  const lignes  = Array.from(tbody ? tbody.querySelectorAll('tr') : []);
  const compteur = document.getElementById('compteur-resultats');
  const vide     = document.getElementById('aucun-resultat');

  // Remplir les selects depuis les données de la colonne correspondante
  selects.forEach(({ selectId, colonne }) => {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const valeurs = new Set();
    lignes.forEach(tr => {
      const td = tr.cells[colonne];
      if (td) valeurs.add(td.textContent.replace(/\s+/g, ' ').trim());
    });
    [...valeurs].sort().forEach(v => {
      if (v) {
        const o = document.createElement('option');
        o.value = v; o.textContent = v;
        sel.appendChild(o);
      }
    });
  });

  function filtrer() {
    const q = input.value.toLowerCase().trim();
    const filtresActifs = selects.map(({ selectId, colonne }) => ({
      colonne,
      valeur: (document.getElementById(selectId) || {}).value || '',
    }));

    let visible = 0;
    lignes.forEach(tr => {
      const texte = tr.textContent.toLowerCase();
      const matchQ = !q || texte.includes(q);
      const matchFiltres = filtresActifs.every(({ colonne, valeur }) => {
        if (!valeur) return true;
        const td = tr.cells[colonne];
        return td && td.textContent.replace(/\s+/g, ' ').trim() === valeur;
      });
      const show = matchQ && matchFiltres;
      tr.style.display = show ? '' : 'none';
      if (show) visible++;
    });

    if (compteur) {
      compteur.textContent = visible + ' / ' + lignes.length
        + ' résultat' + (lignes.length !== 1 ? 's' : '');
    }
    if (vide) vide.classList.toggle('visible', visible === 0 && lignes.length > 0);
  }

  input.addEventListener('input', filtrer);
  selects.forEach(({ selectId }) => {
    const sel = document.getElementById(selectId);
    if (sel) sel.addEventListener('change', filtrer);
  });

  // État initial
  filtrer();
}
