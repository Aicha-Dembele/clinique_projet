/* ═══════════════════════════════════════════════════════════════════
   Recherche instantanée — les listes se filtrent pendant la frappe.

   S'applique tout seul à chaque formulaire de recherche (GET, avec un
   champ name="q") de la page : rien à ajouter dans les gabarits.

   À chaque frappe (après une courte pause), la page est redemandée au
   serveur avec la recherche, exactement comme si on avait cliqué sur
   « Rechercher » — le filtrage reste donc celui des vues Django, avec
   leurs droits d'accès. Puis seules les parties qui ont changé sont
   remplacées : le champ de recherche n'est jamais touché, le curseur
   reste où il est.

   Si la page reçue n'a pas la même structure (cas rare), on recharge
   normalement et on remet le curseur dans le champ.
   ═══════════════════════════════════════════════════════════════════ */
/* La même règle que le serveur (comptes/recherche.py), pour les listes qui
   se filtrent directement dans le navigateur (ex. page des tarifs) :
   chaque mot tapé doit être le début d'un mot du texte, sans tenir compte
   des majuscules ni des accents. */
window.Recherche = (function () {
  var SEPARATEURS = /[-'.@/+(),]/g;
  function normaliser(texte) {
    return (texte || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(SEPARATEURS, ' ');
  }
  function correspond(texte, saisie) {
    var dans = ' ' + normaliser(texte).replace(/\s+/g, ' ');
    return normaliser(saisie).split(/\s+/).filter(Boolean)
      .every(function (mot) { return dans.indexOf(' ' + mot) !== -1; });
  }
  return { normaliser: normaliser, correspond: correspond };
})();

(function () {
  'use strict';

  var DELAI = 250;                 // ms d'attente après la dernière frappe
  var CLE_REPRISE = 'recherche_live_champ';
  var contenu = document.querySelector('#main .content');
  if (!contenu || !window.fetch || !window.DOMParser) return;

  // Après un rechargement de repli : le curseur revient dans le champ.
  try {
    var reprise = sessionStorage.getItem(CLE_REPRISE);
    if (reprise) {
      sessionStorage.removeItem(CLE_REPRISE);
      var champRepris = contenu.querySelector('form input[name="' + reprise + '"]');
      if (champRepris) {
        champRepris.focus();
        var fin = champRepris.value.length;
        if (champRepris.setSelectionRange) champRepris.setSelectionRange(fin, fin);
      }
    }
  } catch (e) { /* stockage indisponible : sans importance */ }

  // Les messages Django (« Patient enregistré »…) n'apparaissent qu'une fois :
  // on les ignore en comparant les deux pages.
  function enfants(el) {
    return Array.prototype.filter.call(el.children, function (n) {
      return !n.classList.contains('alert-c') && n.tagName !== 'SCRIPT';
    });
  }

  function copier(noeud) {
    var copie = document.importNode(noeud, true);
    copie.setAttribute('data-recherche-live', '');
    return copie;
  }

  // Met un côté (avant ou après le formulaire) à jour. Même nombre de blocs :
  // on ne remplace que ceux qui ont changé (pas de clignotement). Sinon (la
  // pagination apparaît, la liste devient vide…) : on remplace tout ce côté.
  function remplacerCote(anciens, neufs, repere, avant) {
    if (anciens.length === neufs.length) {
      anciens.forEach(function (a, i) { if (!a.isEqualNode(neufs[i])) a.replaceWith(copier(neufs[i])); });
      return;
    }
    anciens.forEach(function (a) { a.remove(); });
    neufs.forEach(function (n) {
      if (avant) repere.before(copier(n)); else repere.parentNode.insertBefore(copier(n), null);
    });
  }

  // Remplace tout ce qui a changé, sauf la branche qui contient le formulaire.
  function synchroniser(ancien, neuf, form, formNeuf) {
    var a = enfants(ancien), n = enfants(neuf);
    var ia = a.findIndex(function (x) { return x === form || x.contains(form); });
    var ib = n.findIndex(function (x) { return x === formNeuf || x.contains(formNeuf); });
    if (ia < 0 || ib < 0) return false;
    remplacerCote(a.slice(0, ia), n.slice(0, ib), a[ia], true);
    remplacerCote(a.slice(ia + 1), n.slice(ib + 1), a[ia], false);
    if (a[ia] === form) return true;
    return synchroniser(a[ia], n[ib], form, formNeuf);
  }

  function brancher(form) {
    var champ = form.querySelector('input[name="q"]');
    var methode = (form.getAttribute('method') || 'get').toLowerCase();
    if (!champ || methode !== 'get') return;

    // Uniquement les recherches qui restent sur cette page (pas celles
    // qui mènent à une autre liste).
    var cible = new URL(form.getAttribute('action') || window.location.pathname, window.location.href);
    if (cible.pathname !== window.location.pathname) return;

    var minuterie = null, numero = 0;

    function chercher() {
      var moi = ++numero;
      var url = new URL(cible.href);
      url.search = new URLSearchParams(new FormData(form)).toString();
      form.setAttribute('aria-busy', 'true');

      fetch(url.href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'recherche-live' } })
        .then(function (rep) {
          if (!rep.ok || rep.redirected) throw new Error('réponse inattendue');
          return rep.text();
        })
        .then(function (html) {
          if (moi !== numero) return;            // une frappe plus récente a pris le relais
          var doc = new DOMParser().parseFromString(html, 'text/html');
          var neuf = doc.querySelector('#main .content');
          var champNeuf = neuf && neuf.querySelector('form input[name="q"]');
          if (!champNeuf || !synchroniser(contenu, neuf, form, champNeuf.closest('form'))) {
            throw new Error('structure différente');
          }
          window.history.replaceState(null, '', url.href);
          form.removeAttribute('aria-busy');
        })
        .catch(function () {
          if (moi !== numero) return;
          try { sessionStorage.setItem(CLE_REPRISE, champ.name); } catch (e) { /* idem */ }
          window.location.assign(url.href);
        });
    }

    function plusTard() {
      clearTimeout(minuterie);
      minuterie = setTimeout(chercher, DELAI);
    }

    champ.setAttribute('autocomplete', 'off');
    champ.addEventListener('input', plusTard);
    Array.prototype.forEach.call(form.querySelectorAll('select'), function (s) {
      s.addEventListener('change', plusTard);
    });
    form.addEventListener('submit', function (e) {   // Entrée : tout de suite
      e.preventDefault();
      clearTimeout(minuterie);
      chercher();
    });
  }

  Array.prototype.forEach.call(contenu.querySelectorAll('form'), brancher);
})();
