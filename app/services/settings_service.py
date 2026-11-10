from datetime import datetime

from sqlalchemy.exc import OperationalError, ProgrammingError

from app.extensions import db
from app.models import AppSetting
from app.services import audit_service

MODO_QR = "QR"
MODO_TALONARIO = "BOOKLET"
MODOS_VENTA = (MODO_QR, MODO_TALONARIO)

ETIQUETAS_MODO = {
    MODO_QR: "Ticket con QR",
    MODO_TALONARIO: "Talonario físico",
}

DEFAULTS = {
    "sales_mode": MODO_QR,
    "ticket_validity_days": "1",
    "booklet_low_threshold": "20",
}

LIMITES = {
    "ticket_validity_days": (0, 365),
    "booklet_low_threshold": (1, 10000),
}


def get_setting(clave):
    try:
        fila = db.session.get(AppSetting, clave)
    except (OperationalError, ProgrammingError):
        # La tabla todavía no existe (falta ejecutar upgrade-db): se usan
        # los valores por defecto para que la pantalla de error sea clara
        # en vez de romperse en cada página.
        db.session.rollback()
        return DEFAULTS[clave]
    return fila.value if fila else DEFAULTS[clave]


def get_modo_venta():
    valor = get_setting("sales_mode")
    return valor if valor in MODOS_VENTA else MODO_QR


def get_validez_dias():
    """Días de vigencia de una entrada con QR contando el día de la venta
    (1 = solo el mismo día). 0 = sin vencimiento."""
    try:
        return max(0, int(get_setting("ticket_validity_days")))
    except (TypeError, ValueError):
        return int(DEFAULTS["ticket_validity_days"])


def get_umbral_aviso():
    try:
        return max(1, int(get_setting("booklet_low_threshold")))
    except (TypeError, ValueError):
        return int(DEFAULTS["booklet_low_threshold"])


class AjusteError(ValueError):
    pass


def _validar(clave, valor):
    valor = str(valor).strip()
    if clave == "sales_mode":
        if valor not in MODOS_VENTA:
            raise AjusteError("Modo de venta inválido.")
        return valor
    if clave in LIMITES:
        minimo, maximo = LIMITES[clave]
        if not valor.isdigit():
            raise AjusteError("Debe ser un número entero.")
        numero = int(valor)
        if not minimo <= numero <= maximo:
            raise AjusteError(f"Debe estar entre {minimo} y {maximo}.")
        return str(numero)
    raise AjusteError(f"Ajuste desconocido: {clave}")


def set_setting(clave, valor, usuario):
    """Guarda un ajuste (sin commit) y lo anota en la auditoría si cambió."""
    valor = _validar(clave, valor)
    anterior = get_setting(clave)
    fila = db.session.get(AppSetting, clave)
    if fila is None:
        fila = AppSetting(key=clave, value=valor)
        db.session.add(fila)
    fila.value = valor
    fila.updated_at = datetime.now()
    fila.updated_by = usuario.id
    if anterior != valor:
        audit_service.registrar(
            "ajuste.cambiar",
            entidad="app_setting",
            detalle=f"{clave}: {anterior} -> {valor}",
            usuario=usuario,
        )
    return anterior != valor
