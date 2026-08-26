/*
 * combobox.js — <select> filtrable, sans dépendance externe.
 * S'applique aux selects avec 6+ options.
 * data-no-combobox sur un <select> pour l'exclure.
 *
 * La liste est position:fixed (coordonnées calculées) pour éviter
 * tout problème de z-index ou d'overflow sur les parents.
 */

(function () {
  "use strict";

  // Un seul élément liste en dehors du flux pour toute la page
  const globalListe = document.createElement("ul");
  globalListe.className = "combo-liste";
  globalListe.setAttribute("role", "listbox");
  globalListe.setAttribute("hidden", "");
  document.body.appendChild(globalListe);

  let comboActif = null;   // instance du combobox dont la liste est ouverte

  function init(select) {
    if (select._comboReset) return;
    if (
      select.getAttribute("data-no-combobox") !== null ||
      select.multiple ||
      select.size > 1 ||
      (select.options.length < 2 && select.getAttribute("data-combobox") === null)
    ) return;

    const premierOpt = select.options[0];
    const placeholder = premierOpt && !premierOpt.value
      ? premierOpt.text.replace(/^[-–—\s]+/, "").trim()
      : "Chercher…";

    /* ── Wrapper ──────────────────────────────────────────────────── */
    const wrapper = document.createElement("div");
    wrapper.className = "combo";
    // Transférer les styles de largeur/flex
    const s = select.style;
    if (s.width)    wrapper.style.width    = s.width;
    if (s.flex)     wrapper.style.flex     = s.flex;
    if (s.minWidth) wrapper.style.minWidth = s.minWidth;
    if (s.flexShrink !== undefined) wrapper.style.flexShrink = s.flexShrink;

    /* ── Input de saisie ──────────────────────────────────────────── */
    const saisie = document.createElement("input");
    saisie.type         = "text";
    saisie.className    = "combo-saisie";
    saisie.autocomplete = "off";
    saisie.spellcheck   = false;
    saisie.placeholder  = placeholder;
    saisie.setAttribute("role", "combobox");
    saisie.setAttribute("aria-expanded", "false");
    saisie.setAttribute("aria-autocomplete", "list");
    if (select.required) saisie.required = true;

    /* ── Valeur initiale ──────────────────────────────────────────── */
    if (select.value) {
      const opt = Array.from(select.options).find(o => o.value === select.value);
      if (opt) saisie.value = opt.text.trim();
    }

    /* ── État ─────────────────────────────────────────────────────── */
    let ouvert       = false;
    let indexActif   = -1;
    let blurTimeout  = null;
    let scrollOff    = null;

    /* ── Lecture dynamique des options (gère disabled ajouté/retiré) ─ */
    function lireOptions() {
      return Array.from(select.options).filter(o => o.value);
    }

    /* ── Escape HTML ──────────────────────────────────────────────── */
    function esc(str) {
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    /* ── Positionner la liste sous le champ ───────────────────────── */
    function positionner() {
      const r = saisie.getBoundingClientRect();
      globalListe.style.top   = (r.bottom + 2) + "px";
      globalListe.style.left  = r.left + "px";
      globalListe.style.width = r.width + "px";
    }

    /* ── Construire la liste filtrée ──────────────────────────────── */
    function construireListe(q) {
      globalListe.innerHTML = "";
      indexActif = -1;
      const qLow = q.toLowerCase().trim();
      const options = lireOptions();
      const matching = qLow
        ? options.filter(o => o.text.toLowerCase().includes(qLow))
        : options;

      matching.forEach(opt => {
        const li = document.createElement("li");
        li.className = "combo-option";
        li.setAttribute("role", "option");
        li.dataset.value = opt.value;

        // Transférer les data-* de l'option vers le li (pour les accès JS externes)
        Array.from(opt.attributes)
          .filter(a => a.name.startsWith("data-"))
          .forEach(a => li.setAttribute(a.name, a.value));

        if (opt.disabled) {
          li.classList.add("combo-option--disabled");
          li.setAttribute("aria-disabled", "true");
        }

        // Mise en évidence de la correspondance
        if (qLow) {
          const texte = opt.text.trim();
          const idx = texte.toLowerCase().indexOf(qLow);
          li.innerHTML =
            esc(texte.slice(0, idx)) +
            "<mark>" + esc(texte.slice(idx, idx + q.trim().length)) + "</mark>" +
            esc(texte.slice(idx + q.trim().length));
        } else {
          li.textContent = opt.text.trim();
        }

        li.addEventListener("mousedown", e => {
          e.preventDefault();
          if (!opt.disabled) choisir(opt);
        });
        globalListe.appendChild(li);
      });

      if (!matching.length) {
        const li = document.createElement("li");
        li.className = "combo-vide";
        li.textContent = "Aucun résultat.";
        globalListe.appendChild(li);
      }
    }

    /* ── Ouvrir / fermer ──────────────────────────────────────────── */
    function ouvrir() {
      // Fermer l'autre combobox ouvert si besoin
      if (comboActif && comboActif !== self) comboActif.fermerExterne();

      construireListe(saisie.value);
      positionner();
      globalListe.removeAttribute("hidden");
      saisie.setAttribute("aria-expanded", "true");
      ouvert = true;
      comboActif = self;

      scrollOff = () => { if (ouvert) positionner(); };
      window.addEventListener("scroll", scrollOff, { passive: true, capture: true });
      window.addEventListener("resize", scrollOff, { passive: true });
    }

    function fermer() {
      if (!ouvert) return;
      globalListe.setAttribute("hidden", "");
      saisie.setAttribute("aria-expanded", "false");
      ouvert = false;
      indexActif = -1;
      comboActif = null;
      if (scrollOff) {
        window.removeEventListener("scroll", scrollOff, { capture: true });
        window.removeEventListener("resize", scrollOff);
        scrollOff = null;
      }
    }

    /* ── Sélectionner une option ──────────────────────────────────── */
    function choisir(opt) {
      saisie.value = opt.text.trim();
      select.value = opt.value;
      fermer();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    /* ── Navigation clavier ───────────────────────────────────────── */
    function naviguer(dir) {
      const items = Array.from(
        globalListe.querySelectorAll(".combo-option:not(.combo-option--disabled)")
      );
      if (!items.length) return;
      items[indexActif]?.classList.remove("combo-actif");
      indexActif = Math.min(Math.max(indexActif + dir, 0), items.length - 1);
      items[indexActif].classList.add("combo-actif");
      items[indexActif].scrollIntoView({ block: "nearest" });
    }

    /* ── Événements ───────────────────────────────────────────────── */
    saisie.addEventListener("focus", () => {
      clearTimeout(blurTimeout);   // ← annule la fermeture différée
      ouvrir();
    });

    saisie.addEventListener("input", () => {
      if (ouvert) construireListe(saisie.value);
      else ouvrir();
      if (!saisie.value.trim()) {
        select.value = "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    saisie.addEventListener("keydown", e => {
      switch (e.key) {
        case "ArrowDown": e.preventDefault(); if (!ouvert) ouvrir(); naviguer(1); break;
        case "ArrowUp":   e.preventDefault(); naviguer(-1); break;
        case "Enter": {
          e.preventDefault();
          const actif = globalListe.querySelector(".combo-actif");
          if (actif) {
            const opt = lireOptions().find(o => o.value === actif.dataset.value);
            if (opt && !opt.disabled) choisir(opt);
          }
          break;
        }
        case "Escape": fermer(); saisie.blur(); break;
        case "Tab": fermer(); break;
      }
    });

    saisie.addEventListener("blur", () => {
      blurTimeout = setTimeout(() => {
        fermer();
        // Remet le texte en cohérence avec la valeur du select
        if (select.value) {
          const opt = lireOptions().find(o => o.value === select.value);
          if (opt) saisie.value = opt.text.trim();
        } else {
          saisie.value = "";
        }
      }, 180);
    });

    /* ── API publique ─────────────────────────────────────────────── */
    select._comboReset = () => {
      saisie.value = "";
      select.value = "";
    };

    // Référence pour fermeture externe (un seul combobox ouvert à la fois)
    const self = { fermerExterne: fermer };

    /* ── Insertion DOM ────────────────────────────────────────────── */
    select.style.display = "none";
    select.removeAttribute("required");
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(saisie);
    wrapper.appendChild(select);
  }

  /* ── Fermer en cliquant ailleurs ────────────────────────────────── */
  document.addEventListener("mousedown", e => {
    if (!globalListe.contains(e.target) && comboActif) {
      // On laisse le blur des inputs gérer la fermeture
    }
  }, true);

  /* ── Initialisation ──────────────────────────────────────────────── */
  function initTous() {
    document.querySelectorAll("select").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTous);
  } else {
    initTous();
  }

  // Exposé pour les selects ajoutés dynamiquement après DOMContentLoaded
  window.initCombobox = init;
})();
