from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import DailyClosure
from app.services import audit_service
from app.services.reportes_service import resumen_por_fecha
from app.utils.money import ErrorValidacion, a_decimal, parsear_precio


class CierreError(Exception):
    """Error de negocio al intentar registrar o reabrir un cierre diario."""


def dia_cerrado(fecha):
    """True si ya existe un cierre para esa fecha."""
    return (
        db.session.scalar(
            select(DailyClosure.id).where(DailyClosure.closure_date == fecha).limit(1)
        )
        is not None
    )


def crear_cierre(closure_date, closed_by_user, cash_counted=None, notes=None):
    """Registra el cierre diario de `closure_date` calculado con datos
    reales de ventas y tickets (vía resumen_por_fecha).

    Reglas:
    - No se puede cerrar una fecha futura.
    - Un día solo se cierra una vez (aviso previo + restricción UNIQUE
      como respaldo ante dos cierres simultáneos).
    - Si se indica el efectivo contado en caja, se guarda para comparar
      con el efectivo esperado.
    """
    if closure_date > date.today():
        raise CierreError("No se puede cerrar una fecha futura.")

    if dia_cerrado(closure_date):
        raise CierreError(f"Ya existe un cierre registrado para el {closure_date:%d/%m/%Y}.")

    contado = None
    if cash_counted not in (None, ""):
        try:
            contado = parsear_precio(str(cash_counted), maximo=a_decimal(10**7))
        except ErrorValidacion as error:
            raise CierreError(f"Efectivo contado: {error}")

    notas = (notes or "").strip()
    if len(notas) > 300:
        raise CierreError("Las observaciones no pueden superar los 300 caracteres.")

    resumen = resumen_por_fecha(closure_date)

    cierre = DailyClosure(
        closed_by=closed_by_user.id,
        closure_date=closure_date,
        total_tickets=resumen["total_tickets_vendidos"],
        total_used_tickets=resumen["total_tickets_utilizados"],
        total_amount=resumen["total_recaudado"],
        total_cash=resumen["total_efectivo"],
        total_qr=resumen["total_qr"],
        total_physical_tickets=resumen["total_tickets_fisicos"],
        total_voided_tickets=resumen["tickets_anulados"] + resumen["numeros_anulados"],
        total_voided_amount=resumen["monto_anulado"],
        cash_counted=contado,
        notes=notas or None,
    )
    db.session.add(cierre)
    db.session.flush()

    detalle = (
        f"{closure_date:%d/%m/%Y}: {cierre.total_tickets} tickets, "
        f"Bs {a_decimal(cierre.total_amount)} "
        f"(efectivo {a_decimal(cierre.total_cash)}, QR {a_decimal(cierre.total_qr)})"
    )
    if contado is not None:
        detalle += f"; contado {contado}; diferencia {contado - a_decimal(cierre.total_cash)}"
    audit_service.registrar(
        "cierre.crear",
        entidad="daily_closure",
        entidad_id=cierre.id,
        detalle=detalle,
        usuario=closed_by_user,
    )

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise CierreError(f"Ya existe un cierre registrado para el {closure_date:%d/%m/%Y}.")

    return cierre


def reabrir_cierre(cierre_id, motivo, usuario):
    """Elimina el cierre para poder corregir el día y volver a cerrarlo.
    Exige un motivo y deja una copia de los totales en la auditoría."""
    cierre = db.session.get(DailyClosure, cierre_id)
    if cierre is None:
        raise CierreError("El cierre no existe.")

    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise CierreError("Escribe el motivo de la reapertura (mínimo 5 caracteres).")

    audit_service.registrar(
        "cierre.reabrir",
        entidad="daily_closure",
        entidad_id=cierre.id,
        detalle=(
            f"{cierre.closure_date:%d/%m/%Y}: tickets {cierre.total_tickets}, "
            f"Bs {a_decimal(cierre.total_amount)} (efectivo {a_decimal(cierre.total_cash)}, "
            f"QR {a_decimal(cierre.total_qr)}); cerrado por usuario #{cierre.closed_by}; "
            f"motivo: {motivo}"
        ),
        usuario=usuario,
    )
    fecha = cierre.closure_date
    db.session.delete(cierre)
    db.session.commit()
    return fecha
