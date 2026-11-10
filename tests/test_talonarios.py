import threading

import pytest

from app.extensions import db
from app.models import BookletVoid, Sale, Ticket
from app.services import talonarios_service as ts
from app.services.talonarios_service import TalonarioError
from app.services.ventas_service import VentaError, anular_venta, crear_venta
from tests.helpers import categoria, modo_talonario, talonario, usuario


def numeros(sale):
    return sorted(t.physical_number for i in sale.sale_items for t in i.tickets)


def test_ejemplo_del_museo_249_y_nueve_vendidos(app):
    with app.app_context():
        modo_talonario()
        t = talonario("Mayores", 249, 500)
        mayores = categoria("Mayores")
        venta = crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": mayores.id, "quantity": 9}])
        db.session.commit()
        assert numeros(venta) == list(range(249, 258))
        assert float(venta.total_amount) == 45.0
        assert venta.is_booklet
        assert all(x.status == "USED" for i in venta.sale_items for x in i.tickets)
        db.session.refresh(t)
        assert t.next_number == 258 and t.remaining == 500 - 258 + 1


def test_numeros_consecutivos_entre_ventas_y_por_categoria(app):
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 1, 50)
        talonario("Menores", 100, 150)
        m, n = categoria("Mayores"), categoria("Menores")
        v1 = crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 2}, {"ticket_category_id": n.id, "quantity": 3}])
        v2 = crear_venta(usuario("vendedor2"), "QR", [{"ticket_category_id": m.id, "quantity": 1}])
        db.session.commit()
        por_cat = {i.ticket_category.name: sorted(x.physical_number for x in i.tickets) for i in v1.sale_items}
        assert por_cat == {"Mayores": [1, 2], "Menores": [100, 101, 102]}
        assert numeros(v2) == [3]


def test_venta_que_cruza_dos_talonarios(app):
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 1, 5)
        talonario("Mayores", 6, 10)
        m = categoria("Mayores")
        v = crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 8}])
        db.session.commit()
        assert numeros(v) == list(range(1, 9))


def test_stock_insuficiente_no_deja_nada_a_medias(app):
    with app.app_context():
        modo_talonario()
        t = talonario("Mayores", 1, 5)
        m = categoria("Mayores")
        with pytest.raises(VentaError):
            crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 6}])
        db.session.rollback()
        db.session.refresh(t)
        assert t.next_number == 1
        assert Sale.query.count() == 0 and Ticket.query.count() == 0


def test_sin_talonario_no_se_puede_vender(app):
    with app.app_context():
        modo_talonario()
        with pytest.raises(VentaError):
            crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 1}])


def test_agotado_y_alertas(app):
    with app.app_context():
        modo_talonario()
        assert {a["nivel"] for a in ts.alertas_talonarios()} == {"sin"}
        talonario("Mayores", 1, 25)
        m = categoria("Mayores")
        crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 10}])
        db.session.commit()
        niveles = {a["categoria"]: a["nivel"] for a in ts.alertas_talonarios()}
        assert niveles["Mayores"] == "bajo"   # quedan 15 <= 20
        crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 15}])
        db.session.commit()
        niveles = {a["categoria"]: a["nivel"] for a in ts.alertas_talonarios()}
        assert niveles["Mayores"] == "agotado"
        fila = [f for f in ts.resumen_talonarios() if f["categoria"].name == "Mayores"][0]
        assert fila["sugerido_inicio"] == 26


def test_rangos_que_se_superponen_se_rechazan(app):
    with app.app_context():
        talonario("Mayores", 100, 200)
        for a, b in [(150, 250), (50, 100), (100, 200), (120, 130)]:
            with pytest.raises(TalonarioError):
                ts.registrar_talonario(categoria("Mayores").id, a, b, usuario("admin"))
        db.session.rollback()
        # otra categoría puede reutilizar los mismos números
        talonario("Menores", 100, 200)
        talonario("Mayores", 201, 300)


@pytest.mark.parametrize("a,b", [("abc", "5"), ("5", "x"), ("10", "5"), ("-1", "5"), ("", ""), ("1.5", "9")])
def test_rangos_invalidos(app, a, b):
    with app.app_context():
        with pytest.raises(TalonarioError):
            ts.registrar_talonario(categoria("Mayores").id, a, b, usuario("admin"))


def test_anular_numero_se_consume_y_no_suma(app):
    with app.app_context():
        modo_talonario()
        t = talonario("Mayores", 249, 300)
        m = categoria("Mayores")
        ts.anular_numeros(m.id, 1, "dañado", usuario("admin"))
        db.session.commit()
        assert [v.number for v in BookletVoid.query.all()] == [249]
        v = crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 2}])
        db.session.commit()
        assert numeros(v) == [250, 251]
        with pytest.raises(TalonarioError):
            ts.anular_numeros(m.id, 1, "", usuario("admin"))


def test_anular_venta_no_reutiliza_numeros(app):
    with app.app_context():
        modo_talonario()
        t = talonario("Mayores", 1, 10)
        m = categoria("Mayores")
        v = crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 3}])
        db.session.commit()
        anular_venta(v.id, "error de cobro", usuario("admin"))
        db.session.commit()
        db.session.refresh(v)
        assert v.is_voided
        assert all(x.status == "CANCELLED" for i in v.sale_items for x in i.tickets)
        v2 = crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": m.id, "quantity": 1}])
        db.session.commit()
        assert numeros(v2) == [4]
        with pytest.raises(VentaError):
            anular_venta(v.id, "otra vez", usuario("admin"))
        with pytest.raises(VentaError):
            anular_venta(v2.id, "x", usuario("vendedor1"))  # no admin


def test_cerrar_talonario_deja_de_entregar(app):
    with app.app_context():
        modo_talonario()
        t = talonario("Mayores", 1, 10)
        ts.cerrar_talonario(t.id, "extraviado", usuario("admin"))
        db.session.commit()
        with pytest.raises(VentaError):
            crear_venta(usuario("vendedor1"), "CASH", [{"ticket_category_id": categoria("Mayores").id, "quantity": 1}])


def test_reserva_concurrente_nunca_repite_numeros(app, tmp_path):
    """Varios hilos venden a la vez: cada número se entrega exactamente una vez."""
    with app.app_context():
        modo_talonario()
        talonario("Mayores", 1, 60)
        cid = categoria("Mayores").id
        uid = usuario("vendedor1").id
    resultados, errores = [], []

    def vender():
        with app.app_context():
            try:
                from app.models import User
                u = db.session.get(User, uid)
                v = crear_venta(u, "CASH", [{"ticket_category_id": cid, "quantity": 5}])
                db.session.commit()
                resultados.extend(numeros(v))
            except Exception as e:  # noqa
                db.session.rollback()
                errores.append(e)
            finally:
                db.session.remove()

    hilos = [threading.Thread(target=vender) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert not errores, errores
    assert sorted(resultados) == list(range(1, 41))
