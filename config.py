import os
from datetime import timedelta
from decimal import Decimal

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))

# Carga las variables de .env al entorno del proceso. Se hace acá,
# antes de que la clase Config lea os.environ, para que .env se
# respete sin importar cómo se arranque la aplicación: "python run.py",
# "waitress-serve run:app" o "flask run".
load_dotenv(os.path.join(basedir, ".env"))


def _bool(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _int(nombre, defecto):
    try:
        return int(os.environ.get(nombre, defecto))
    except (TypeError, ValueError):
        return defecto


class Config:
    """Configuración base de la aplicación.

    DATABASE_URL permite intercambiar SQLite (desarrollo / un solo
    equipo) por PostgreSQL sin tocar el código. Si no se define, se usa
    SQLite dentro de instance/.

    SECRET_KEY: si no se define (o es una clave conocida/débil), la
    aplicación genera una clave aleatoria propia y la guarda en
    instance/secret.key (ver app/__init__.py). Nunca hace falta
    inventar una a mano.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY") or None

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(basedir, "instance", "museo.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Sesión y cookies -------------------------------------------------
    # COOKIE_SECURE=1 solo cuando todo el acceso es por HTTPS (Caddy);
    # con HTTP plano la cookie "Secure" no se enviaría y nadie podría
    # iniciar sesión. iniciar_https.bat ya lo activa.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("COOKIE_SECURE")
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool("COOKIE_SECURE")

    # Los formularios de un mostrador pueden quedar abiertos todo el día:
    # el token CSRF vale mientras dure la sesión, no solo una hora.
    WTF_CSRF_TIME_LIMIT = None

    # BEHIND_PROXY=1 cuando Caddy (u otro proxy) va delante de Waitress,
    # para ver la IP real de cada dispositivo. No activarlo si Waitress
    # recibe conexiones directas: X-Forwarded-For se podría falsificar.
    BEHIND_PROXY = _bool("BEHIND_PROXY")

    # --- Límites de negocio -----------------------------------------------
    MAX_TICKETS_POR_VENTA = _int("MAX_TICKETS_POR_VENTA", 300)
    PRECIO_MAXIMO = Decimal(os.environ.get("PRECIO_MAXIMO", "9999.99"))
    MAX_NUMEROS_POR_TALONARIO = 100000
    FILAS_POR_PAGINA = 50

    # --- Protección contra adivinar contraseñas -----------------------------
    LOGIN_MAX_INTENTOS = _int("LOGIN_MAX_INTENTOS", 5)
    LOGIN_VENTANA_SEG = _int("LOGIN_VENTANA_SEG", 15 * 60)
    LOGIN_BLOQUEO_SEG = _int("LOGIN_BLOQUEO_SEG", 15 * 60)
