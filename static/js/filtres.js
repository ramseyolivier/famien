(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('form.finance-filtres[data-live-filter]');
    var tbody = document.querySelector('table.registre tbody');
    if (!form || !tbody) return;

    function filtrer() {
      var debutInp     = form.querySelector('input[name="debut"]');
      var finInp       = form.querySelector('input[name="fin"]');
      var debutVal     = debutInp ? debutInp.value : '';
      var finVal       = finInp   ? finInp.value   : '';
      var selects      = Array.from(form.querySelectorAll('select[name]'));
      var comboSaisies = Array.from(form.querySelectorAll('.combo-saisie'));

      Array.from(tbody.querySelectorAll('tr')).forEach(function (tr) {
        var ok = true;
        selects.forEach(function (sel) {
          var val = sel.value;
          if (val && tr.dataset[sel.name] !== undefined && tr.dataset[sel.name] !== val) ok = false;
        });
        if (debutVal && tr.dataset.date < debutVal) ok = false;
        if (finVal   && tr.dataset.date > finVal)   ok = false;
        comboSaisies.forEach(function (s) {
          var q = s.value.toLowerCase().trim();
          if (q && !tr.textContent.toLowerCase().includes(q)) ok = false;
        });
        tr.style.display = ok ? '' : 'none';
      });
    }

    form.querySelectorAll('select').forEach(function (s) {
      s.addEventListener('change', filtrer);
    });
    form.querySelectorAll('input[type="date"]').forEach(function (i) {
      i.addEventListener('change', filtrer);
    });
    form.querySelectorAll('.combo-saisie').forEach(function (i) {
      i.addEventListener('input', filtrer);
    });
  });
})();
