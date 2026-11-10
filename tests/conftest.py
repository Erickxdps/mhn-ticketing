import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.security import limitador_login


def _config(ruta_db, csrf=False):
    class TestConfig:
        SECRET_KEY = "clave-de-pruebas-" + "x" * 40
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{ruta_db}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        TESTING = True
        WTF_CSRF_ENABLED = csrf
        WTF_CSRF_TIME_LIMIT = None
        MAX_TICKETS_POR_VENTA = 300
        FILAS_POR_PAGINA = 50
        PRECIO_MAXIMO = __import__("decimal").Decimal("9999.99")
        MAX_NUMEROS_POR_TALONARIO = 100000
        LOGIN_MAX_INTENTOS = 5
        LOGIN_VENTANA_SEG = 900
        LOGIN_BLOQUEO_SEG = 900
        SESSION_COOKIE_HTTPONLY = True
        SESSION_COOKIE_SAMESITE = "Lax"
        BEHIND_PROXY = False
    return TestConfig


def _crear_app(tmp_path, csrf=False):
    from app.db_upgrade import actualizar_base_de_datos

    app = create_app(_config(tmp_path / "test.db", csrf))
    with app.app_context():
        actualizar_base_de_datos(respaldo=False)
        for username, nombre, rol, clave in [
            ("admin", "Administrador General", "ADMIN", "Admin-12345"),
            ("vendedor1", "Vendedor Uno", "SELLER", "Vendedor-12345"),
            ("vendedor2", "Vendedor Dos", "SELLER", "Vendedor-12345"),
            ("inspector1", "Inspector Uno", "INSPECTOR", "Inspector-12345"),
        ]:
            u = User(username=username, full_name=nombre, role=rol)
            u.set_password(clave)
            db.session.add(u)
        db.session.commit()
    limitador_login.reiniciar()
    return app


@pytest.fixture()
def app(tmp_path):
    app = _crear_app(tmp_path)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def app_csrf(tmp_path):
    app = _crear_app(tmp_path, csrf=True)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


CLAVES = {"admin": "Admin-12345", "vendedor1": "Vendedor-12345", "vendedor2": "Vendedor-12345", "inspector1": "Inspector-12345"}


def iniciar_sesion(client, username):
    return client.post("/login", data={"username": username, "password": CLAVES[username]}, follow_redirects=False)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(app):
    c = app.test_client()
    assert iniciar_sesion(c, "admin").status_code == 302
    return c


@pytest.fixture()
def seller_client(app):
    c = app.test_client()
    assert iniciar_sesion(c, "vendedor1").status_code == 302
    return c


@pytest.fixture()
def inspector_client(app):
    c = app.test_client()
    assert iniciar_sesion(c, "inspector1").status_code == 302
    return c
