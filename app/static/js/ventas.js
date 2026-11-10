(function () {
  const form = document.getElementById("form-venta");
  if (!form) return;

  const esTalonario = window.MHN_MODO_TALONARIO === true;
  const filas = Array.from(form.querySelectorAll("[data-categoria]"));
  const lblCantidad = document.getElementById("resumen-cantidad");
  const lblTotal = document.getElementById("resumen-total");
  const listaRangos = document.getElementById("resumen-rangos");
  const lblError = document.getElementById("resumen-error");
  const btn = document.getElementById("btn-registrar");
  const btnInicialDeshabilitado = btn ? btn.disabled : false;
  const MAX_POR_VENTA = 300;

  function num5(n) {
    return String(n).padStart(5, "0");
  }

  function leerCantidad(input) {
    const n = parseInt(input.value, 10);
    if (isNaN(n) || n < 0) return 0;
    return Math.min(n, 1000);
  }

  // Tramos que se entregarían para `cantidad` boletos a partir de los
  // segmentos disponibles (misma lógica que el servidor). Devuelve
  // {tramos, faltan}.
  function simular(segmentos, cantidad) {
    const tramos = [];
    let faltan = cantidad;
    for (const seg of segmentos) {
      if (faltan <= 0) break;
      const disponibles = seg[1] - seg[0] + 1;
      const toma = Math.min(disponibles, faltan);
      tramos.push([seg[0], seg[0] + toma - 1]);
      faltan -= toma;
    }
    return { tramos: tramos, faltan: faltan };
  }

  function texto(tramos) {
    return tramos
      .map(function (t) {
        return t[0] === t[1] ? num5(t[0]) : num5(t[0]) + " – " + num5(t[1]);
      })
      .join(" y ");
  }

  function actualizar() {
    let total = 0;
    let cantidadTotal = 0;
    let hayError = false;
    let mensajeError = "";
    if (listaRangos) listaRangos.innerHTML = "";

    filas.forEach(function (fila) {
      const input = fila.querySelector("input[type=number]");
      const cantidad = leerCantidad(input);
      const precio = parseFloat(fila.dataset.precio);
      total += cantidad * precio;
      cantidadTotal += cantidad;

      if (esTalonario && cantidad > 0) {
        const segmentos = fila.dataset.segmentos ? JSON.parse(fila.dataset.segmentos) : [];
        const r = simular(segmentos, cantidad);
        const li = document.createElement("li");
        const nombre = document.createElement("strong");
        nombre.textContent = fila.dataset.nombre + ": ";
        li.appendChild(nombre);
        if (r.faltan > 0) {
          hayError = true;
          const disp = segmentos.reduce(function (a, s) { return a + (s[1] - s[0] + 1); }, 0);
          mensajeError = "No hay suficientes boletos de " + fila.dataset.nombre + " (quedan " + disp + ").";
          li.appendChild(document.createTextNode("sin boletos suficientes"));
          li.className = "text-danger";
        } else {
          const span = document.createElement("span");
          span.className = "mhn-range";
          span.textContent = texto(r.tramos);
          li.appendChild(span);
        }
        listaRangos.appendChild(li);
      }
    });

    if (cantidadTotal > MAX_POR_VENTA) {
      hayError = true;
      mensajeError = "Máximo " + MAX_POR_VENTA + " boletos por venta.";
    }

    lblCantidad.textContent = cantidadTotal;
    lblTotal.textContent = total.toFixed(2);
    if (lblError) {
      lblError.textContent = mensajeError;
      lblError.classList.toggle("d-none", !hayError);
    }
    if (btn) btn.disabled = btnInicialDeshabilitado || cantidadTotal === 0 || hayError;
  }

  form.addEventListener("click", function (e) {
    const b = e.target.closest("[data-paso]");
    if (!b) return;
    const input = b.parentElement.querySelector("input");
    const nuevo = Math.max(0, Math.min(1000, leerCantidad(input) + parseInt(b.dataset.paso, 10)));
    input.value = nuevo;
    actualizar();
  });
  form.addEventListener("input", actualizar);
  window.addEventListener("pageshow", actualizar);
  actualizar();
})();
