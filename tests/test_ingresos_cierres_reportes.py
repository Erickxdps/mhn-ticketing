from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import Ticket
from app.services import settings_service
from app.services.cierres_service import CierreError, crear_cierre, dia_cerrado, reabrir_cierre
from app.services.ingresos_service import validar_entrada
from app.services.ventas_service import VentaError, anular_venta, crear_venta
from tests.helpers import categoria, modo_talonario, talonario, usuario


def vender_qr(n=1, user="vendedor1"):
    v = crear_venta(usuario(user), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": n}])
    db.session.commit()
    return v


def test_ingreso_valido_y_luego_ya_usado(app):
    with app.app_context():
        code = vender_qr().sale_items[0].tickets[0].ticket_code
        assert validar_entrada(code)["status"] == "VALID"
        assert validar_entrada(code)["status"] == "ALREADY_USED"
        assert validar_entrada("MHN-NO-EXISTE")["status"] == "NOT_FOUND"
        assert validar_entrada("")["status"] == "NOT_FOUND"


def test_ingreso_por_token_qr(app):
    with app.app_context():
        t = vender_qr().sale_items[0].tickets[0]
        assert validar_entrada(t.qr_token)["status"] == "VALID"


def test_ingreso_entrada_anulada(app):
    with app.app_context():
        v = vender_qr()
        code = v.sale_items[0].tickets[0].ticket_code
        anular_venta(v.id, "error", usuario("admin"))
        db.session.commit()
        assert validar_entrada(code)["status"] == "CANCELLED"


def test_ingreso_vencida_y_sin_vencimiento(app):
    with app.app_context():
        t = vender_qr().sale_items[0].tickets[0]
        t.sold_at = datetime.now() - timedelta(days=3)
        db.session.commit()
        code = t.ticket_code
        assert validar_entrada(code)["status"] == "EXPIRED"
        settings_service.set_setting("ticket_validity_days", "0", usuario("admin"))
        db.session.commit()
        assert validar_entrada(code)["status"] == "VALID"


def test_boleto_de_talonario_no_se_valida(app):
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 1, 10)
        v = vender_qr()
        t = v.sale_items[0].tickets[0]
        assert validar_entrada(t.ticket_code)["status"] == "PHYSICAL"
        assert validar_entrada(t.qr_token)["status"] == "PHYSICAL"


def test_validacion_concurrente_solo_una_vale(app):
    import threading
    with app.app_context():
        code = vender_qr().sale_items[0].tickets[0].ticket_code
    res = []

    def ir():
        with app.app_context():
            res.append(validar_entrada(code)["status"])
            db.session.remove()

    hs = [threading.Thread(target=ir) for _ in range(6)]
    [h.start() for h in hs]
    [h.join() for h in hs]
    assert res.count("VALID") == 1 and res.count("ALREADY_USED") == 5


def test_cierre_bloquea_ventas_y_anulaciones_y_se_puede_reabrir(app):
    with app.app_context():
        v = vender_qr(2)
        cierre = crear_cierre(date.today(), usuario("admin"), cash_counted="10", notes="ok")
        db.session.commit()
        assert float(cierre.total_amount) == 10.0 and float(cierre.total_cash) == 10.0
        assert float(cierre.cash_difference) == 0.0
        assert dia_cerrado(date.today())
        with pytest.raises(VentaError):
            vender_qr()
        db.session.rollback()
        with pytest.raises(VentaError):
            anular_venta(v.id, "x", usuario("admin"))
        db.session.rollback()
        with pytest.raises(CierreError):
            crear_cierre(date.today(), usuario("admin"))
        db.session.rollback()
        with pytest.raises(CierreError):
            crear_cierre(date.today() + timedelta(days=1), usuario("admin"))
        db.session.rollback()
        reabrir_cierre(cierre.id, "corregir", usuario("admin"))
        db.session.commit()
        assert not dia_cerrado(date.today())
        vender_qr()


def test_cierre_con_talonario_registra_rangos_y_diferencia(app):
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 249, 500)
        vender_qr(9)
        from app.services.reportes_service import resumen_por_fecha
        r = resumen_por_fecha(date.today())
        t = r["talonarios"][0]
        assert (t["desde"], t["hasta"], t["vendidos"]) == (249, 257, 9)
        assert float(r["total_recaudado"]) == 45.0 and r["total_tickets_fisicos"] == 9
        cierre = crear_cierre(date.today(), usuario("admin"), cash_counted="40")
        db.session.commit()
        assert float(cierre.cash_difference) == -5.0


def test_resumen_por_categoria_y_metodo_de_pago(app):
    with app.app_context():
        from app.services.reportes_service import resumen_por_fecha
        crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 2},
                                                 {"ticket_category_id": categoria("Extranjeros").id, "quantity": 1}])
        crear_venta(usuario("vendedor1"), "QR", [{"ticket_category_id": categoria("Cortesía").id, "quantity": 3}])
        db.session.commit()
        r = resumen_por_fecha(date.today())
        assert float(r["total_efectivo"]) == 22.0 and float(r["total_qr"]) == 6.0 and float(r["total_recaudado"]) == 28.0
        assert r["desglose_categoria"]["Mayores"] == 2 and r["desglose_categoria"]["Cortesía"] == 3


def test_reportes_filtros_paginacion_y_csv(app, admin_client):
    with app.app_context():
        for _ in range(3):
            vender_qr()
    html = admin_client.get("/reportes/ventas?fecha_inicio=2000-01-01&fecha_fin=2000-01-02").get_data(as_text=True)
    assert "No hay ventas" in html
    assert "No hay ventas" not in admin_client.get(f"/reportes/ventas?fecha_inicio={date.today()}&fecha_fin={date.today()}").get_data(as_text=True)
    r = admin_client.get("/reportes/ventas?formato=csv")
    assert r.mimetype == "text/csv" and r.get_data(as_text=True).startswith("﻿")
    assert admin_client.get("/reportes/entradas?formato=csv").status_code == 200
    assert admin_client.get("/reportes/ventas?fecha_inicio=basura").status_code == 200
    assert admin_client.get("/reportes/entradas?status=XX&tipo=YY&pagina=-4").status_code == 200


def test_paginacion_muchas_filas(app, admin_client):
    with app.app_context():
        for _ in range(55):
            vender_qr()
    html = admin_client.get("/reportes/ventas").get_data(as_text=True)
    assert "Página" in html and "Siguiente" in html
    assert admin_client.get("/reportes/ventas?pagina=2").status_code == 200


def test_auditoria_registra_acciones(app, admin_client):
    admin_client.post("/configuracion/categorias/1", data={"name": "Mayores", "price": "7", "is_active": "on"})
    html = admin_client.get("/auditoria").get_data(as_text=True)
    assert "Mayores" in html and "7" in html


def test_cambio_de_modo_se_audita_y_se_refleja(app, admin_client):
    admin_client.post("/configuracion/ajustes", data={"sales_mode": "BOOKLET", "ticket_validity_days": "1", "booklet_low_threshold": "20"})
    html = admin_client.get("/ventas").get_data(as_text=True)
    assert "Talonario" in html
    r = admin_client.post("/configuracion/ajustes", data={"sales_mode": "XX", "ticket_validity_days": "1", "booklet_low_threshold": "20"}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert settings_service.get_modo_venta() == settings_service.MODO_TALONARIO
