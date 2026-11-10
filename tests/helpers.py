from app.extensions import db
from app.models import TicketCategory, User
from app.services import settings_service, talonarios_service


def categoria(nombre):
    return db.session.query(TicketCategory).filter_by(name=nombre).one()


def usuario(username):
    return db.session.query(User).filter_by(username=username).one()


def modo_talonario():
    settings_service.set_setting("sales_mode", settings_service.MODO_TALONARIO, usuario("admin"))
    db.session.commit()


def talonario(nombre, primero, ultimo):
    t = talonarios_service.registrar_talonario(categoria(nombre).id, primero, ultimo, usuario("admin"))
    db.session.commit()
    return t
