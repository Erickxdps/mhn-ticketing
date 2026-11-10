"""Piezas de seguridad compartidas: política de contraseñas, validación
de la URL de retorno tras el login y bloqueo temporal por intentos
fallidos."""

import threading
import time
from urllib.parse import urlsplit

from flask import current_app

# --------------------------------------------------------------------------
# Contraseñas
# --------------------------------------------------------------------------

LARGO_MINIMO_PASSWORD = 8
LARGO_MAXIMO_PASSWORD = 128

# Lista corta de contraseñas que cualquiera probaría primero.
PASSWORDS_COMUNES = {
    "12345678", "123456789", "1234567890", "87654321", "11111111", "00000000",
    "password", "password1", "password123", "contraseña", "contrasena",
    "contraseña1", "qwertyui", "qwerty123", "abcd1234", "admin123", "admin1234",
    "administrador", "museo123", "museo1234", "museo2024", "museo2025",
    "museo2026", "bolivia123", "lapaz1234", "iloveyou",
}


def validar_password(password, username=None):
    """Devuelve un mensaje de error (str) si la contraseña no cumple la
    política, o None si es aceptable."""
    if password is None or len(password) < LARGO_MINIMO_PASSWORD:
        return f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres."
    if len(password) > LARGO_MAXIMO_PASSWORD:
        return f"La contraseña no puede superar los {LARGO_MAXIMO_PASSWORD} caracteres."
    if password.isdigit():
        return "La contraseña no puede estar formada solo por números."
    if len(set(password)) == 1:
        return "La contraseña no puede repetir siempre el mismo carácter."
    if password.lower() in PASSWORDS_COMUNES:
        return "Esa contraseña es demasiado común. Elige otra."
    if username and password.lower() == username.strip().lower():
        return "La contraseña no puede ser igual al nombre de usuario."
    return None


# --------------------------------------------------------------------------
# Redirección tras el login
# --------------------------------------------------------------------------

def destino_seguro(destino):
    """True solo si `destino` es una ruta interna ("/ventas?x=1").
    Rechaza URLs absolutas, esquemas, "//host" y barras invertidas, que
    permitirían llevar al usuario a otro sitio después de iniciar sesión."""
    if not destino or not isinstance(destino, str):
        return False
    if "\\" in destino or "\n" in destino or "\r" in destino:
        return False
    partes = urlsplit(destino)
    if partes.scheme or partes.netloc:
        return False
    return destino.startswith("/") and not destino.startswith("//")


# --------------------------------------------------------------------------
# Bloqueo temporal por intentos fallidos de inicio de sesión
# --------------------------------------------------------------------------

class LimitadorLogin:
    """Cuenta intentos fallidos en memoria (el sistema corre en un solo
    proceso). Dos llaves independientes:

    - usuario + IP: tras LOGIN_MAX_INTENTOS fallos se bloquea esa
      combinación; un atacante no puede dejar fuera a otra persona
      desde otro equipo.
    - solo IP: umbral mayor (x6), frena a quien prueba muchos usuarios
      distintos desde un mismo equipo.
    """

    FACTOR_IP = 6
    MAX_LLAVES = 5000

    def __init__(self):
        self._lock = threading.Lock()
        self._fallos = {}      # llave -> [timestamps]
        self._bloqueos = {}    # llave -> timestamp en que termina el bloqueo

    @staticmethod
    def _llaves(usuario, ip):
        return (f"u:{(usuario or '').strip().lower()}|{ip}", f"i:{ip}")

    def _cfg(self):
        cfg = current_app.config
        return (
            cfg.get("LOGIN_MAX_INTENTOS", 5),
            cfg.get("LOGIN_VENTANA_SEG", 900),
            cfg.get("LOGIN_BLOQUEO_SEG", 900),
        )

    def _limpiar(self, ahora, ventana):
        if len(self._fallos) + len(self._bloqueos) < self.MAX_LLAVES:
            return
        self._fallos = {
            k: [t for t in v if ahora - t < ventana] for k, v in self._fallos.items()
        }
        self._fallos = {k: v for k, v in self._fallos.items() if v}
        self._bloqueos = {k: t for k, t in self._bloqueos.items() if t > ahora}

    def segundos_bloqueado(self, usuario, ip):
        """Segundos que faltan para poder reintentar (0 si no está bloqueado)."""
        ahora = time.time()
        with self._lock:
            restantes = [
                self._bloqueos[k] - ahora
                for k in self._llaves(usuario, ip)
                if self._bloqueos.get(k, 0) > ahora
            ]
        return int(max(restantes)) + 1 if restantes else 0

    def registrar_fallo(self, usuario, ip):
        """Anota un intento fallido. Devuelve True si con este fallo se
        activó un bloqueo."""
        maximo, ventana, bloqueo = self._cfg()
        ahora = time.time()
        bloqueado = False
        with self._lock:
            self._limpiar(ahora, ventana)
            llave_usuario, llave_ip = self._llaves(usuario, ip)
            for llave, tope in ((llave_usuario, maximo), (llave_ip, maximo * self.FACTOR_IP)):
                recientes = [t for t in self._fallos.get(llave, []) if ahora - t < ventana]
                recientes.append(ahora)
                self._fallos[llave] = recientes
                if len(recientes) >= tope:
                    self._bloqueos[llave] = ahora + bloqueo
                    self._fallos[llave] = []
                    bloqueado = True
        return bloqueado

    def registrar_exito(self, usuario, ip):
        with self._lock:
            llave_usuario, _ = self._llaves(usuario, ip)
            self._fallos.pop(llave_usuario, None)
            self._bloqueos.pop(llave_usuario, None)

    def reiniciar(self):
        with self._lock:
            self._fallos.clear()
            self._bloqueos.clear()


limitador_login = LimitadorLogin()
