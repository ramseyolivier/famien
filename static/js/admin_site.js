(function () {
  'use strict';

  function majChamps() {
    var type = document.getElementById('id_type');
    if (!type) return;

    var rowCommune   = document.querySelector('.field-commune');
    var rowMagasin   = document.querySelector('.field-magasin_rattachement');
    var rowRemise    = document.querySelector('.field-remise_convention');

    var val = type.value;

    if (rowCommune)  rowCommune.style.display  = (val === 'DEPOT') ? 'none' : '';
    if (rowMagasin)  rowMagasin.style.display  = (val === 'ECOLE') ? '' : 'none';
    if (rowRemise)   rowRemise.style.display   = (val === 'DEPOT') ? 'none' : '';
  }

  document.addEventListener('DOMContentLoaded', function () {
    majChamps();
    var type = document.getElementById('id_type');
    if (type) type.addEventListener('change', majChamps);
  });
})();
