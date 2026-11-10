(function () {
  const cat = document.getElementById("tal-categoria");
  const primero = document.getElementById("tal-primero");
  const ultimo = document.getElementById("tal-ultimo");
  const sugerencia = document.getElementById("tal-sugerencia");
  const total = document.getElementById("tal-total");
  if (!cat || !primero || !ultimo) return;

  function num5(n) { return String(n).padStart(5, "0"); }

  function sugerir() {
    const opt = cat.options[cat.selectedIndex];
    const s = opt ? parseInt(opt.dataset.sugerido, 10) : NaN;
    if (isNaN(s)) { sugerencia.textContent = ""; return; }
    sugerencia.textContent = "Sugerido: " + num5(s);
    if (!primero.dataset.tocado) primero.value = s;
  }

  function calcular() {
    const a = parseInt(primero.value, 10), b = parseInt(ultimo.value, 10);
    if (isNaN(a) || isNaN(b)) { total.textContent = ""; return; }
    total.textContent = b < a
      ? "El último número no puede ser menor que el primero."
      : "Talonario del " + num5(a) + " al " + num5(b) + ": " + (b - a + 1) + " boletos.";
  }

  cat.addEventListener("change", function () { delete primero.dataset.tocado; sugerir(); calcular(); });
  primero.addEventListener("input", function () { primero.dataset.tocado = "1"; calcular(); });
  ultimo.addEventListener("input", calcular);
  sugerir();
  calcular();
})();
