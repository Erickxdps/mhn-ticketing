import shutil
from pathlib import Path

from sqlalchemy import inspect

from app import create_app
from app.db_upgrade import actualizar_base_de_datos, hay_pendientes
from app.extensions import db
from app.models import Sale, Ticket, TicketCategory

LEGADO = Path(__file__).parent / "fixtures" / "legacy_v9.db"


def _app_con_legado(tmp_path):
    destino = tmp_path / "legado.db"
    shutil.copy(LEGADO, destino)

    class Cfg:
        SECRET_KEY = "k" * 48
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{destino}"
        TESTING = True
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        WTF_CSRF_ENABLED = False
    return create_app(Cfg)


def test_actualiza_base_vieja_conservando_datos_y_es_idempotente(tmp_path):
    app = _app_con_legado(tmp_path)
    with app.app_context():
        assert hay_pendientes()
        acciones = actualizar_base_de_datos(respaldo=False)
        assert acciones
        assert not hay_pendientes()
        assert actualizar_base_de_datos(respaldo=False) == []   # segunda vez: nada que hacer

        nombres = [c.name for c in TicketCategory.query.order_by(TicketCategory.id)]
        assert nombres[:3] == ["Mayores", "Menores", "Extranjeros"]       # renombradas, mismos ids
        assert {"Tercera edad", "Cortesía"} <= set(nombres)
        precios = {c.name: float(c.price) for c in TicketCategory.query.all()}
        # Los precios que ya tenían las categorías existentes se conservan; las nuevas nacen con su precio base.
        assert precios == {"Mayores": 15.0, "Menores": 8.0, "Extranjeros": 30.0, "Tercera edad": 2.0, "Cortesía": 2.0}

        assert Sale.query.count() == 1 and Ticket.query.count() == 2
        venta = Sale.query.one()
        assert venta.sales_mode == "QR" and venta.status == "ACTIVE"
        cols = {c["name"] for c in inspect(db.engine).get_columns("tickets")}
        assert {"booklet_id", "physical_number"} <= cols
        assert "ticket_booklets" in inspect(db.engine).get_table_names()


def test_crea_respaldo_antes_de_actualizar(tmp_path, monkeypatch):
    import backup_db
    monkeypatch.setattr(backup_db, "basedir", str(tmp_path))
    app = _app_con_legado(tmp_path)
    with app.app_context():
        actualizar_base_de_datos(respaldo=True)
    copias = list((tmp_path / "instance" / "backups").glob("pre_actualizacion_*.db"))
    assert len(copias) == 1


def test_la_app_actualizada_funciona_sobre_la_base_vieja(tmp_path):
    app = _app_con_legado(tmp_path)
    with app.app_context():
        actualizar_base_de_datos(respaldo=False)
    c = app.test_client()
    assert c.post("/login", data={"username": "admin", "password": "admin12345"}).status_code == 302
    for url in ["/ventas", "/dashboard", "/reportes", "/talonarios", "/cierres"]:
        assert c.get(url).status_code == 200, url
