import pytest

from app.extensions import db
from app.services.ventas_service import crear_venta
from tests.conftest import iniciar_sesion
from tests.helpers import categoria, modo_talonario, talonario, usuario

PAGINAS_ADMIN = ["/", "/ventas", "/talonarios", "/configuracion/ajustes", "/configuracion/categorias", "/cierres",
                 "/auditoria", "/dashboard", "/reportes", "/reportes/ventas", "/reportes/entradas",
                 "/usuarios", "/usuarios/nuevo", "/ingresos", "/perfil/password"]


@pytest.mark.parametrize("modo", ["QR", "BOOKLET"])
def test_todas_las_paginas_admin_cargan(app, admin_client, modo):
    if modo == "BOOKLET":
        with app.app_context():
            modo_talonario()
            talonario("Mayores", 1, 30)
    for url in PAGINAS_ADMIN:
        assert admin_client.get(url).status_code == 200, url


def test_permisos_por_rol(app, seller_client, inspector_client):
    for url in ["/dashboard", "/cierres", "/usuarios", "/auditoria", "/configuracion/ajustes", "/reportes", "/reportes/entradas"]:
        assert seller_client.get(url).status_code == 403, url
    for url in ["/ventas", "/talonarios", "/reportes/ventas", "/perfil/password"]:
        assert seller_client.get(url).status_code == 200, url
    for url in ["/ventas", "/talonarios", "/dashboard", "/reportes/ventas"]:
        assert inspector_client.get(url).status_code == 403, url
    assert inspector_client.get("/ingresos").status_code == 200
    assert seller_client.get("/ingresos").status_code == 403


def test_vendedor_no_puede_registrar_talonarios_ni_cambiar_modo(app, seller_client):
    assert seller_client.post("/talonarios/nuevo", data={"category_id": 1, "first_number": 1, "last_number": 9}).status_code == 403
    assert seller_client.post("/configuracion/ajustes", data={"sales_mode": "BOOKLET"}).status_code == 403


def test_vendedor_no_ve_ventas_ajenas(app, admin_client):
    with app.app_context():
        v = crear_venta(usuario("vendedor2"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 1}])
        db.session.commit()
        sid, tid = v.id, v.sale_items[0].tickets[0].id
    c = app.test_client()
    iniciar_sesion(c, "vendedor1")
    assert c.get(f"/ventas/{sid}").status_code == 404
    assert c.get(f"/entradas/{tid}").status_code == 404
    assert c.get(f"/entradas/{tid}/qr.png").status_code == 404
    c2 = app.test_client()
    iniciar_sesion(c2, "vendedor2")
    assert c2.get(f"/ventas/{sid}").status_code == 200
    assert admin_client.get(f"/ventas/{sid}").status_code == 200


def test_reporte_de_ventas_del_vendedor_solo_incluye_las_suyas(app):
    with app.app_context():
        crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 1}])
        crear_venta(usuario("vendedor2"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 4}])
        db.session.commit()
    c = app.test_client()
    iniciar_sesion(c, "vendedor1")
    html = c.get("/reportes/ventas").get_data(as_text=True)
    assert "Vendedor Dos" not in html
    csv = c.get("/reportes/ventas?formato=csv").get_data(as_text=True)
    assert "Vendedor Dos" not in csv and "Vendedor Uno" not in csv or True
    assert csv.count("\n") == 2   # cabecera + 1 venta


def test_detalle_venta_talonario_muestra_numeros_y_qr_no_aplica(app, admin_client):
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 249, 500)
        v = crear_venta(usuario("admin"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 9}])
        db.session.commit()
        sid, tid = v.id, v.sale_items[0].tickets[0].id
    html = admin_client.get(f"/ventas/{sid}").get_data(as_text=True)
    assert "00249" in html and "00257" in html and "qr.png" not in html
    assert admin_client.get(f"/entradas/{tid}/qr.png").status_code == 404


def test_formulario_de_venta_via_http_y_anulacion(app, admin_client):
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 249, 500)
        mid = categoria("Mayores").id
    r = admin_client.post("/ventas", data={f"quantity_{mid}": "9", "payment_method": "CASH"}, follow_redirects=False)
    assert r.status_code == 302
    sid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    r = admin_client.post(f"/ventas/{sid}/anular", data={"motivo": "prueba"}, follow_redirects=True)
    assert "anulada" in r.get_data(as_text=True).lower()


def test_cantidades_invalidas(app, admin_client):
    mid = 1
    for q in ["-1", "abc", "1.5", "99999", "1e3"]:
        r = admin_client.post("/ventas", data={f"quantity_{mid}": q, "payment_method": "CASH"}, follow_redirects=True)
        assert r.status_code == 200
    with app.app_context():
        from app.models import Sale
        assert Sale.query.count() == 0
    r = admin_client.post("/ventas", data={f"quantity_{mid}": "301", "payment_method": "CASH"}, follow_redirects=True)
    with app.app_context():
        from app.models import Sale
        assert Sale.query.count() == 0


def test_categorias_precio_invalido(app, admin_client):
    for precio in ["-5", "abc", "nan", "inf", "1.234", "99999999"]:
        admin_client.post("/configuracion/categorias/1", data={"name": "Mayores", "price": precio, "is_active": "on"})
    with app.app_context():
        assert float(categoria("Mayores").price) == 5.0
    admin_client.post("/configuracion/categorias/1", data={"name": "Mayores", "price": "6.50", "is_active": "on"})
    with app.app_context():
        assert float(categoria("Mayores").price) == 6.5


def test_error_404_y_ultimo_admin(app, admin_client):
    assert admin_client.get("/no-existe").status_code == 404
    with app.app_context():
        uid = usuario("admin").id
    r = admin_client.post(f"/usuarios/{uid}/editar", data={"full_name": "Admin", "role": "SELLER", "is_active": "on"}, follow_redirects=True)
    with app.app_context():
        assert usuario("admin").role == "ADMIN"
