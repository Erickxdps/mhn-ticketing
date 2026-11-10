import re

import pytest

from app.extensions import db
from app.security import destino_seguro, limitador_login, validar_password
from tests.conftest import CLAVES, iniciar_sesion


def token(client):
    html = client.get("/login").get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def test_csrf_bloquea_post_sin_token(app_csrf):
    c = app_csrf.test_client()
    r = c.post("/login", data={"username": "admin", "password": CLAVES["admin"]})
    assert r.status_code == 400


def test_csrf_acepta_con_token_y_json(app_csrf):
    c = app_csrf.test_client()
    t = token(c)
    r = c.post("/login", data={"username": "admin", "password": CLAVES["admin"], "csrf_token": t})
    assert r.status_code == 302
    r = c.post("/ingresos/validar", json={"codigo": "x"})
    assert r.status_code == 400 and r.is_json
    meta = re.search(r'name="csrf-token" content="([^"]+)"', c.get("/ingresos").get_data(as_text=True)).group(1)
    r = c.post("/ingresos/validar", json={"codigo": "x"}, headers={"X-CSRFToken": meta})
    assert r.status_code == 200 and r.get_json()["status"] == "NOT_FOUND"


def _logueado(c):
    return c.get("/ventas").status_code == 200


def test_login_incorrecto_y_bloqueo(app):
    c = app.test_client()
    for _ in range(5):
        r = c.post("/login", data={"username": "admin", "password": "mala"})
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    # Bloqueado: ni siquiera la clave correcta entra
    r = c.post("/login", data={"username": "admin", "password": CLAVES["admin"]})
    assert "/login" in r.headers["Location"] and not _logueado(c)
    limitador_login.reiniciar()
    assert iniciar_sesion(c, "admin").status_code == 302 and _logueado(c)


def test_usuario_inactivo_no_entra(app):
    from tests.helpers import usuario
    with app.app_context():
        usuario("vendedor2").is_active = False
        db.session.commit()
    c = app.test_client()
    r = iniciar_sesion(c, "vendedor2")
    assert "/login" in r.headers["Location"] and not _logueado(c)


@pytest.mark.parametrize("destino,esperado", [
    ("/ventas", True), ("//evil.com", False), ("https://evil.com", False),
    ("/\\evil.com", False), ("javascript:alert(1)", False), ("", False),
])
def test_next_solo_rutas_internas(app, destino, esperado):
    with app.test_request_context():
        assert destino_seguro(destino) == esperado


def test_login_redirige_a_next_interno_y_rechaza_externo(app):
    c = app.test_client()
    r = c.post("/login", data={"username": "admin", "password": CLAVES["admin"], "next": "/ventas"})
    assert r.headers["Location"].endswith("/ventas")
    c2 = app.test_client()
    r = c2.post("/login", data={"username": "admin", "password": CLAVES["admin"], "next": "https://evil.com"})
    assert "evil.com" not in r.headers["Location"]


def test_politica_de_contrasenas():
    assert validar_password("corta1", "u")
    assert validar_password("12345678", "u")
    assert validar_password("password", "u")
    assert validar_password("usuario-123", "usuario-123")
    assert not validar_password("Una-Clave-Larga-9", "otro")


def test_ajax_sin_sesion_devuelve_401_json(client):
    r = client.post("/ingresos/validar", json={"codigo": "x"}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 401 and r.is_json


def test_paginas_privadas_redirigen_al_login(client):
    for url in ["/", "/ventas", "/dashboard", "/talonarios", "/cierres", "/usuarios", "/auditoria"]:
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"], url


def test_cookies_httponly_samesite(app):
    c = app.test_client()
    r = c.post("/login", data={"username": "admin", "password": CLAVES["admin"]})
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "HttpOnly" in cookies and "SameSite=Lax" in cookies


def test_secret_key_se_genera_si_falta(tmp_path, monkeypatch):
    from app import create_app
    monkeypatch.delenv("SECRET_KEY", raising=False)

    class Cfg:
        SECRET_KEY = None
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'k.db'}"
        TESTING = True
        SQLALCHEMY_TRACK_MODIFICATIONS = False
    a = create_app(Cfg)
    assert a.config["SECRET_KEY"] and len(a.config["SECRET_KEY"]) >= 32
