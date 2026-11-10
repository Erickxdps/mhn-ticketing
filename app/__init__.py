import logging
import os
import secrets
import warnings
from logging.handlers import RotatingFileHandler

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from app.extensions import csrf, db, login_manager, migrate
from app.security import destino_seguro
from app.utils.money import formatear_bs, formatear_numero_boleto

# Claves que aparecen en ejemplos o documentación: nunca son secretas.
CLAVES_CONOCIDAS = {
    "dev-secret-key-cambiar",
    "cambiar-esta-clave-en-produccion",
    "cambiar-esta-clave",
    "changeme",
    "secret",
    "secret-key",
    "test",
}
LARGO_MINIMO_CLAVE = 32


@event.listens_for(Engine, "connect")
def _configurar_sqlite(dbapi_connection, _registro):
    """Ajustes de SQLite que no vienen activados de fábrica:

    - foreign_keys: que una venta no pueda apuntar a un usuario inexistente.
    - journal_mode=WAL: lecturas y escrituras simultáneas sin bloquearse
      (varios vendedores e inspectores a la vez).
    - busy_timeout: esperar hasta 10 s en vez de fallar con
      "database is locked" si otro equipo está escribiendo.
    """
    import sqlite3

    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _resolver_secret_key(app):
    """Garantiza una SECRET_KEY segura sin que nadie tenga que inventarla.

    - Si SECRET_KEY viene del entorno y es larga y no es de ejemplo, se usa.
    - Si falta, es corta o es una clave conocida (como la de .env.example),
      se genera una aleatoria y se guarda en instance/secret.key para que
      sobreviva a los reinicios (si cambiara, todas las sesiones se
      cerrarían).
    """
    clave = (app.config.get("SECRET_KEY") or "").strip()
    if clave and clave not in CLAVES_CONOCIDAS and len(clave) >= LARGO_MINIMO_CLAVE:
        app.config["SECRET_KEY"] = clave
        return
    if app.testing and clave:
        return  # las pruebas fijan su propia clave corta

    if clave:
        warnings.warn(
            "SECRET_KEY es de ejemplo o demasiado corta: se ignora y se usa una "
            "clave aleatoria propia guardada en instance/secret.key.",
            stacklevel=2,
        )

    ruta = os.path.join(app.instance_path, "secret.key")
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            guardada = archivo.read().strip()
        if len(guardada) >= LARGO_MINIMO_CLAVE:
            app.config["SECRET_KEY"] = guardada
            return
    except OSError:
        pass

    nueva = secrets.token_hex(32)
    try:
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(nueva)
        try:
            os.chmod(ruta, 0o600)
        except OSError:
            pass
    except OSError:
        warnings.warn(
            "No se pudo guardar instance/secret.key: la clave será temporal y las "
            "sesiones se cerrarán al reiniciar.",
            stacklevel=2,
        )
    app.config["SECRET_KEY"] = nueva


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    _resolver_secret_key(app)

    # En SQLite el dinero se guarda como número decimal; todo valor se
    # redondea a 2 decimales antes de guardarse, así que el aviso de
    # SQLAlchemy sobre Decimal no aplica.
    warnings.filterwarnings(
        "ignore", message=r".*does \*not\* support Decimal objects natively.*"
    )

    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _configurar_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def respuesta_no_autenticado():
        """Sin sesión: las páginas redirigen al login (recordando a dónde
        iba el usuario); las llamadas AJAX reciben un 401 en JSON para
        poder avisar «tu sesión venció» sin confundirse con un fallo de red."""
        if _espera_json():
            return (
                jsonify(
                    success=False,
                    status="UNAUTHENTICATED",
                    message="Tu sesión venció. Vuelve a iniciar sesión.",
                    ticket=None,
                ),
                401,
            )
        flash(login_manager.login_message, login_manager.login_message_category)
        destino = None
        if request.method == "GET":
            destino = request.full_path if request.query_string else request.path
            if not destino_seguro(destino):
                destino = None
        return redirect(url_for("auth.login", next=destino))

    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_helpers(app)

    from app.cli import register_cli

    register_cli(app)

    return app


def _espera_json():
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    mejor = request.accept_mimetypes.best
    return mejor == "application/json"


def _configurar_logging(app):
    """Escribe los eventos importantes (errores, intentos sin permiso,
    inicios de sesión, ventas, cierres) a un archivo rotativo dentro de
    instance/logs/, además de la consola. No se activa en pruebas."""
    if app.testing:
        return

    carpeta_logs = os.path.join(app.instance_path, "logs")
    os.makedirs(carpeta_logs, exist_ok=True)

    manejador = RotatingFileHandler(
        os.path.join(carpeta_logs, "museo.log"),
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    manejador.setLevel(logging.INFO)
    manejador.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    app.logger.addHandler(manejador)
    app.logger.setLevel(logging.INFO)
    app.logger.info("=== Servidor iniciado ===")


def _register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def error_csrf(error):
        usuario = current_user.username if current_user.is_authenticated else "(sin sesión)"
        app.logger.warning(f"CSRF rechazado — usuario={usuario} ruta={request.path} motivo={error.description}")
        if _espera_json():
            return (
                jsonify(
                    success=False,
                    status="CSRF",
                    message="La página está desactualizada. Recárgala e inténtalo de nuevo.",
                    ticket=None,
                ),
                400,
            )
        return render_template("errors/400.html"), 400

    @app.errorhandler(401)
    def error_401(error):
        return app.login_manager.unauthorized()

    @app.errorhandler(403)
    def error_403(error):
        usuario = current_user.username if current_user.is_authenticated else "(sin sesión)"
        app.logger.warning(f"403 Forbidden — usuario={usuario} ruta={request.path}")
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def error_404(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def error_500(error):
        # Flask ya registra el traceback completo del error original.
        return render_template("errors/500.html"), 500


def _register_template_helpers(app):
    from app.services import settings_service, talonarios_service

    app.jinja_env.filters["bs"] = formatear_bs
    app.jinja_env.filters["num5"] = formatear_numero_boleto

    @app.context_processor
    def globales():
        datos = {
            "MODO_QR": settings_service.MODO_QR,
            "MODO_TALONARIO": settings_service.MODO_TALONARIO,
            "modo_venta": settings_service.MODO_QR,
            "alertas_nav": 0,
        }
        if not current_user.is_authenticated:
            return datos
        datos["modo_venta"] = settings_service.get_modo_venta()
        if (
            datos["modo_venta"] == settings_service.MODO_TALONARIO
            and current_user.role in ("ADMIN", "SELLER")
        ):
            try:
                datos["alertas_nav"] = len(talonarios_service.alertas_talonarios())
            except Exception:  # pragma: no cover - no debe romper ninguna página
                db.session.rollback()
        return datos


def _register_blueprints(app):
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.usuarios import usuarios_bp
    from app.routes.ventas import ventas_bp
    from app.routes.entradas import entradas_bp
    from app.routes.ingresos import ingresos_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.reportes import reportes_bp
    from app.routes.cierres import cierres_bp
    from app.routes.configuracion import configuracion_bp
    from app.routes.talonarios import talonarios_bp
    from app.routes.auditoria import auditoria_bp

    for blueprint in (
        main_bp,
        auth_bp,
        usuarios_bp,
        ventas_bp,
        entradas_bp,
        ingresos_bp,
        dashboard_bp,
        reportes_bp,
        cierres_bp,
        configuracion_bp,
        talonarios_bp,
        auditoria_bp,
    ):
        app.register_blueprint(blueprint)
