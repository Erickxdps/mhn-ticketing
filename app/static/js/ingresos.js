(function () {
  const input = document.getElementById("codigo");
  const resultado = document.getElementById("resultado");
  const historial = document.getElementById("historial");
  const botonVaciar = document.getElementById("vaciar-historial");
  if (!input) return;

  const ESTILOS = {
    VALID: { clase: "valid", icono: "bi-check-circle-fill", titulo: "Entrada válida", badge: "success" },
    ALREADY_USED: { clase: "already_used", icono: "bi-exclamation-triangle-fill", titulo: "Entrada ya utilizada", badge: "warning" },
    CANCELLED: { clase: "cancelled", icono: "bi-x-circle-fill", titulo: "Entrada anulada", badge: "secondary" },
    EXPIRED: { clase: "already_used", icono: "bi-calendar-x-fill", titulo: "Entrada vencida", badge: "warning" },
    PHYSICAL: { clase: "cancelled", icono: "bi-journal-bookmark-fill", titulo: "Boleto de talonario", badge: "secondary" },
    NOT_FOUND: { clase: "not_found", icono: "bi-question-circle-fill", titulo: "Entrada no encontrada", badge: "danger" },
    ERROR: { clase: "not_found", icono: "bi-wifi-off", titulo: "No se pudo validar", badge: "danger" },
  };

  const STORAGE_KEY = "mhn_ingresos_historial";
  const MAX_ITEMS = 30;
  const TEXTO_VACIO = "Todavía no validaste ninguna entrada en esta sesión.";

  function el(tag, clase, texto) {
    const e = document.createElement(tag);
    if (clase) e.className = clase;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function leerGuardado() {
    try {
      const crudo = sessionStorage.getItem(STORAGE_KEY);
      const datos = crudo ? JSON.parse(crudo) : [];
      return Array.isArray(datos) ? datos : [];
    } catch (e) { return []; }
  }

  function guardar(items) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS))); } catch (e) { /* sin storage */ }
  }

  function itemHistorial(entrada) {
    const item = el("div", "mhn-history-item");
    item.appendChild(el("span", "mhn-history-code", String(entrada.codigo)));
    const clase = ["success", "warning", "secondary", "danger"].indexOf(entrada.badge) >= 0 ? entrada.badge : "secondary";
    item.appendChild(el("span", "badge text-bg-" + clase, String(entrada.status)));
    return item;
  }

  function mostrarVacio() {
    historial.textContent = "";
    const p = el("p", "mhn-muted small mb-0", TEXTO_VACIO);
    p.id = "historial-vacio";
    historial.appendChild(p);
  }

  function restaurar() {
    const items = leerGuardado();
    if (items.length === 0) return;
    historial.textContent = "";
    items.forEach(function (e) { historial.appendChild(itemHistorial(e)); });
  }

  function agregar(entrada) {
    const vacio = document.getElementById("historial-vacio");
    if (vacio) vacio.remove();
    historial.prepend(itemHistorial(entrada));
    const items = leerGuardado();
    items.unshift(entrada);
    guardar(items);
  }

  botonVaciar.addEventListener("click", function () {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* nada */ }
    mostrarVacio();
  });
  restaurar();

  function pintar(estilo, mensaje, ticket) {
    resultado.className = "mhn-scan-result status-" + estilo.clase;
    resultado.textContent = "";
    const icono = el("div", "mhn-scan-icon");
    icono.appendChild(el("i", "bi " + estilo.icono));
    resultado.appendChild(icono);
    resultado.appendChild(el("div", "mhn-scan-status", estilo.titulo));
    resultado.appendChild(el("p", "mhn-scan-message", mensaje));
    if (ticket) {
      const dl = el("dl", "mhn-scan-details");
      const filas = [
        ["Código", ticket.ticket_code],
        ["Categoría", ticket.category],
        ["Vendida", ticket.sold_at || "-"],
        ["Ingreso registrado", ticket.used_at || "-"],
      ];
      if (ticket.physical_number) filas.splice(1, 0, ["N.º de boleto", ticket.physical_number]);
      filas.forEach(function (f) {
        dl.appendChild(el("dt", null, f[0]));
        dl.appendChild(el("dd", null, String(f[1])));
      });
      resultado.appendChild(dl);
    }
  }

  function tokenCsrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  async function validar(codigo) {
    try {
      const respuesta = await fetch(window.MHN_URL_VALIDAR, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-CSRFToken": tokenCsrf(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ codigo: codigo }),
      });
      let data = null;
      try { data = await respuesta.json(); } catch (e) { /* respuesta no JSON */ }

      if (respuesta.status === 401) {
        pintar(ESTILOS.ERROR, "La sesión venció. Vuelve a iniciar sesión.", null);
        return;
      }
      if (!data || !data.status) {
        pintar(ESTILOS.ERROR, "La página está desactualizada. Recárgala e inténtalo de nuevo.", null);
        return;
      }
      const estilo = ESTILOS[data.status] || ESTILOS.NOT_FOUND;
      pintar(estilo, data.message || estilo.titulo, data.ticket);
      agregar({
        codigo: data.ticket ? data.ticket.ticket_code : codigo.slice(0, 40),
        status: data.status,
        badge: estilo.badge,
      });
    } catch (error) {
      pintar(ESTILOS.ERROR, "No se pudo conectar con el servidor. Inténtalo nuevamente.", null);
    }
  }

  input.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const codigo = input.value.trim();
    if (!codigo) return;
    validar(codigo);
    input.value = "";
    input.focus();
  });

  // ---- Cámara (jsQR local) -------------------------------------------
  const toggleBtn = document.getElementById("toggle-camara");
  const wrap = document.getElementById("camara-wrap");
  const video = document.getElementById("camara-video");
  const canvas = document.getElementById("camara-canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const estadoCamara = document.getElementById("camara-estado");
  const flash = document.getElementById("camara-flash");

  let stream = null, animando = false, ultimoCodigo = null, ultimoTs = 0;
  const COOLDOWN_MS = 2500;

  function avisoCamara(mensaje) { estadoCamara.textContent = mensaje; estadoCamara.classList.remove("d-none"); }

  async function iniciarCamara() {
    if (typeof jsQR !== "function") { avisoCamara("No se pudo cargar el lector de QR. Usa el campo de texto."); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      avisoCamara("Este navegador no permite acceder a la cámara (¿falta HTTPS?). Usa el campo de texto.");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      video.srcObject = stream;
      await video.play();
      wrap.classList.remove("d-none");
      toggleBtn.innerHTML = '<i class="bi bi-camera-video-off"></i> Detener cámara';
      estadoCamara.classList.add("d-none");
      input.blur();
      animando = true;
      requestAnimationFrame(frame);
    } catch (error) {
      avisoCamara("No se pudo acceder a la cámara (permiso denegado, sin cámara, o la página no usa HTTPS/localhost).");
    }
  }

  function detenerCamara() {
    animando = false;
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    wrap.classList.add("d-none");
    toggleBtn.innerHTML = '<i class="bi bi-camera"></i> Usar cámara';
  }

  function frame() {
    if (!animando) return;
    if (video.readyState === video.HAVE_ENOUGH_DATA) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const qr = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
      if (qr && qr.data) {
        const ahora = Date.now();
        if (!(qr.data === ultimoCodigo && ahora - ultimoTs < COOLDOWN_MS)) {
          ultimoCodigo = qr.data; ultimoTs = ahora;
          flash.classList.add("is-active");
          setTimeout(function () { flash.classList.remove("is-active"); }, 200);
          validar(qr.data);
        }
      }
    }
    requestAnimationFrame(frame);
  }

  toggleBtn.addEventListener("click", function () { stream ? detenerCamara() : iniciarCamara(); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) detenerCamara(); });
  window.addEventListener("beforeunload", detenerCamara);
})();
