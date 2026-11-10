(function () {
  const shell = document.querySelector(".mhn-shell");
  const toggle = document.querySelector(".mhn-menu-toggle");
  const backdrop = document.querySelector(".mhn-sidebar-backdrop");

  if (!shell || !toggle) return;

  function closeNav() {
    shell.classList.remove("is-nav-open");
  }

  toggle.addEventListener("click", function () {
    shell.classList.toggle("is-nav-open");
  });

  if (backdrop) {
    backdrop.addEventListener("click", closeNav);
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeNav();
  });

  // Cerrar el menú al navegar (mobile) para que no quede abierto
  // al volver con el botón "atrás".
  document.querySelectorAll(".mhn-nav-link").forEach(function (link) {
    link.addEventListener("click", closeNav);
  });
})();

(function () {
  const STORAGE_KEY = "mhn-theme";
  const botones = document.querySelectorAll(".mhn-theme-toggle");
  if (botones.length === 0) return;

  function temaActual() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function actualizarIconos(tema) {
    botones.forEach(function (boton) {
      const icono = boton.querySelector("i");
      if (icono) icono.className = "bi " + (tema === "dark" ? "bi-sun" : "bi-moon-stars");
      boton.setAttribute("aria-label", tema === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
    });
  }

  function aplicarTema(tema) {
    document.documentElement.setAttribute("data-theme", tema);
    try { localStorage.setItem(STORAGE_KEY, tema); } catch (error) { /* se ignora si no hay storage */ }
    actualizarIconos(tema);
  }

  botones.forEach(function (boton) {
    boton.addEventListener("click", function () {
      aplicarTema(temaActual() === "dark" ? "light" : "dark");
    });
  });

  // El atributo data-theme ya lo puso el script anti-parpadeo del
  // <head>; acá solo sincronizamos el ícono del botón con ese estado.
  actualizarIconos(temaActual());
})();

(function () {
  // Evita que un doble clic (o un clic ansioso mientras la página
  // todavía está procesando) mande el mismo formulario dos veces —
  // en /ventas eso significaría cobrar y generar tickets duplicados;
  // en /cierres, intentar crear el cierre dos veces seguidas.
  //
  // Al enviarse un formulario, se deshabilitan sus botones de envío
  // (incluidos los vinculados por el atributo form="..." aunque no
  // estén físicamente adentro del <form>, como en la tabla de
  // categorías) y se muestra un pequeño indicador de carga. Como el
  // deshabilitado ocurre en el propio evento "submit", el envío que
  // ya está en curso no se ve afectado — solo se bloquea un segundo
  // clic mientras se espera la respuesta del servidor.
  function botonesDelFormulario(form) {
    const directos = Array.from(
      form.querySelectorAll('button[type="submit"], input[type="submit"]')
    );
    const vinculados = form.id
      ? Array.from(
          document.querySelectorAll(
            'button[form="' + form.id + '"], input[form="' + form.id + '"]'
          )
        )
      : [];
    return directos.concat(vinculados);
  }

  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      botonesDelFormulario(form).forEach(function (boton) {
        if (boton.disabled) return;
        boton.disabled = true;
        boton.dataset.textoOriginal = boton.innerHTML;
        boton.innerHTML =
          '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Enviando…';
      });
    });
  });
})();
