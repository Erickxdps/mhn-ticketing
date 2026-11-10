"""Talonarios físicos: registro, consulta, reserva atómica de números y
anulación de números.

Idea central: cada categoría tiene uno o más talonarios con un rango de
números impresos (p. ej. 00249–00500). Al vender, el sistema entrega los
siguientes números del rango y avanza el contador (`next_number`). Los
números nunca se reutilizan: lo entregado, lo dañado y lo anulado
quedan registrados.
"""

from datetime import datetime

from flask import current_app
from sqlalchemy import func, select, update

from app.extensions import db
from app.models import BookletVoid, Ticket, TicketBooklet, TicketCategory
from app.services import audit_service, settings_service
from app.utils.money import ErrorValidacion, formatear_numero_boleto, parsear_entero


class TalonarioError(Exception):
    """Error de negocio al operar con talonarios (mensaje apto para mostrar)."""


MAX_NUMERO = 99_999_999
MAX_ANULAR_DE_UNA_VEZ = 20
MAX_REINTENTOS_RESERVA = 6


# --------------------------------------------------------------------------
# Consulta
# --------------------------------------------------------------------------

def _bloques_disponibles(category_id):
    """Talonarios activos con boletos disponibles, del número más bajo al
    más alto. populate_existing fuerza a leer el valor real de la base de
    datos aunque el objeto ya estuviera en memoria."""
    return (
        db.session.execute(
            select(TicketBooklet)
            .where(
                TicketBooklet.ticket_category_id == category_id,
                TicketBooklet.status == "ACTIVE",
                TicketBooklet.next_number <= TicketBooklet.last_number,
            )
            .order_by(TicketBooklet.first_number)
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )


def estado_categoria(categoria, umbral=None):
    """Situación de los talonarios de una categoría.

    nivel: 'sin'      -> nunca se registró un talonario
           'agotado'  -> hay talonarios pero no quedan boletos
           'bajo'     -> quedan pocos (<= umbral de aviso)
           'ok'       -> alcanza
    """
    umbral = umbral or settings_service.get_umbral_aviso()
    bloques = _bloques_disponibles(categoria.id)
    disponibles = sum(b.remaining for b in bloques)

    total_registrados = db.session.scalar(
        select(func.count(TicketBooklet.id)).where(
            TicketBooklet.ticket_category_id == categoria.id
        )
    )
    ultimo_numero = db.session.scalar(
        select(func.max(TicketBooklet.last_number)).where(
            TicketBooklet.ticket_category_id == categoria.id
        )
    )

    if total_registrados == 0:
        nivel = "sin"
    elif disponibles == 0:
        nivel = "agotado"
    elif disponibles <= umbral:
        nivel = "bajo"
    else:
        nivel = "ok"

    actual = bloques[0] if bloques else None
    return {
        "categoria": categoria,
        "bloques": bloques,
        "actual": actual,
        "siguiente": actual.next_number if actual else None,
        "disponibles": disponibles,
        "nivel": nivel,
        "umbral": umbral,
        # Reposición sugerida: continuar justo después del último número
        # registrado (o desde 1 si es el primer talonario).
        "sugerido_inicio": (ultimo_numero + 1) if ultimo_numero is not None else 1,
        # Rangos que todavía se pueden entregar, para la vista previa de la venta.
        "segmentos": [[b.next_number, b.last_number] for b in bloques],
    }


def resumen_talonarios():
    """Estado de todas las categorías activas, en el orden en que se crearon."""
    umbral = settings_service.get_umbral_aviso()
    categorias = (
        db.session.execute(
            select(TicketCategory)
            .where(TicketCategory.is_active.is_(True))
            .order_by(TicketCategory.id)
        )
        .scalars()
        .all()
    )
    return [estado_categoria(c, umbral) for c in categorias]


def alertas_talonarios(resumen=None):
    """Mensajes para avisar al personal. Devuelve una lista de dicts con
    nivel ('sin', 'agotado', 'bajo'), categoría y texto."""
    resumen = resumen if resumen is not None else resumen_talonarios()
    alertas = []
    for fila in resumen:
        nombre = fila["categoria"].name
        if fila["nivel"] == "sin":
            texto = f"{nombre}: no hay ningún talonario registrado."
        elif fila["nivel"] == "agotado":
            texto = f"{nombre}: el talonario se agotó. Registra la reposición."
        elif fila["nivel"] == "bajo":
            n = fila["disponibles"]
            texto = (
                f"{nombre}: queda{'n' if n != 1 else ''} {n} boleto{'s' if n != 1 else ''}. "
                f"Se sugiere registrar la reposición desde el {formatear_numero_boleto(fila['sugerido_inicio'])}."
            )
        else:
            continue
        alertas.append({"nivel": fila["nivel"], "categoria": nombre, "texto": texto})
    return alertas


# --------------------------------------------------------------------------
# Registro y cierre de talonarios
# --------------------------------------------------------------------------

def registrar_talonario(category_id, primero, ultimo, usuario, notas=None):
    """Registra un talonario (o una reposición) con su rango completo.

    `primero` es el primer número que todavía se puede entregar: el
    siguiente boleto que se va a romper del talonario."""
    categoria = db.session.get(TicketCategory, category_id)
    if categoria is None:
        raise TalonarioError("La categoría elegida no existe.")

    try:
        primero = parsear_entero(primero, "El primer número", 0, MAX_NUMERO)
        ultimo = parsear_entero(ultimo, "El último número", 0, MAX_NUMERO)
    except ErrorValidacion as error:
        raise TalonarioError(str(error))

    if ultimo < primero:
        raise TalonarioError("El último número no puede ser menor que el primero.")
    maximo = current_app.config.get("MAX_NUMEROS_POR_TALONARIO", 100000)
    if ultimo - primero + 1 > maximo:
        raise TalonarioError(f"Un talonario no puede tener más de {maximo} boletos.")

    choque = db.session.scalar(
        select(TicketBooklet)
        .where(
            TicketBooklet.ticket_category_id == category_id,
            TicketBooklet.first_number <= ultimo,
            TicketBooklet.last_number >= primero,
        )
        .limit(1)
    )
    if choque is not None:
        raise TalonarioError(
            f"Ese rango se cruza con un talonario ya registrado de {categoria.name} "
            f"({formatear_numero_boleto(choque.first_number)} – "
            f"{formatear_numero_boleto(choque.last_number)}). "
            "Los números no pueden repetirse."
        )

    talonario = TicketBooklet(
        ticket_category_id=category_id,
        first_number=primero,
        last_number=ultimo,
        next_number=primero,
        status="ACTIVE",
        notes=(notas or "").strip()[:200] or None,
        created_by=usuario.id,
    )
    db.session.add(talonario)
    db.session.flush()
    audit_service.registrar(
        "talonario.crear",
        entidad="ticket_booklet",
        entidad_id=talonario.id,
        detalle=f"{categoria.name}: {formatear_numero_boleto(primero)} – {formatear_numero_boleto(ultimo)}",
        usuario=usuario,
    )
    db.session.commit()
    return talonario


def cerrar_talonario(booklet_id, motivo, usuario):
    """Cierra un talonario antes de agotarse (perdido, dañado, reemplazado).
    Los números sin entregar quedan fuera de circulación."""
    talonario = db.session.get(TicketBooklet, booklet_id)
    if talonario is None:
        raise TalonarioError("El talonario no existe.")
    if talonario.status != "ACTIVE":
        raise TalonarioError("Ese talonario ya está cerrado.")
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise TalonarioError("Escribe el motivo del cierre (mínimo 5 caracteres).")

    sin_entregar = max(0, talonario.last_number - talonario.next_number + 1)
    talonario.status = "CLOSED"
    talonario.closed_at = datetime.now()
    talonario.closed_by = usuario.id
    talonario.close_reason = motivo[:200]
    audit_service.registrar(
        "talonario.cerrar",
        entidad="ticket_booklet",
        entidad_id=talonario.id,
        detalle=(
            f"{talonario.ticket_category.name} {talonario.range_label}; "
            f"sin entregar: {sin_entregar}; motivo: {motivo}"
        ),
        usuario=usuario,
    )
    db.session.commit()
    return talonario


# --------------------------------------------------------------------------
# Reserva atómica de números
# --------------------------------------------------------------------------

def reservar_numeros(categoria, cantidad):
    """Reserva `cantidad` números consecutivos de los talonarios de la
    categoría y devuelve [(talonario, numero), ...].

    No hace commit: se usa dentro de la transacción de la venta, así que
    si la venta falla la reserva se deshace con ella.

    Es segura ante dos ventas simultáneas: el contador avanza con un
    UPDATE condicionado al valor que se leyó (`next_number = esperado`).
    Si otra venta se adelantó, el UPDATE no afecta ninguna fila y se
    vuelve a intentar con el valor real. Funciona igual en SQLite y
    PostgreSQL sin bloqueos explícitos.
    """
    if cantidad <= 0:
        raise TalonarioError("La cantidad debe ser mayor que cero.")

    pendiente = cantidad
    reservados = []
    fallos = 0

    while pendiente > 0:
        bloques = _bloques_disponibles(categoria.id)
        if not bloques:
            entregados = cantidad - pendiente
            if entregados == 0 and not _tiene_talonarios(categoria.id):
                raise TalonarioError(
                    f"{categoria.name} no tiene talonario registrado. "
                    "Un administrador debe registrar uno en Talonarios."
                )
            disponibles = cantidad - pendiente
            if disponibles == 0:
                raise TalonarioError(
                    f"El talonario de {categoria.name} se agotó. "
                    "Registra la reposición en Talonarios."
                )
            raise TalonarioError(
                f"No alcanzan los boletos de {categoria.name}: se pidieron {cantidad} y "
                f"solo hay {disponibles} disponibles. Registra la reposición en Talonarios "
                "o vende una cantidad menor."
            )

        bloque = bloques[0]
        toma = min(bloque.remaining, pendiente)
        esperado = bloque.next_number

        resultado = db.session.execute(
            update(TicketBooklet)
            .where(
                TicketBooklet.id == bloque.id,
                TicketBooklet.next_number == esperado,
                TicketBooklet.status == "ACTIVE",
                TicketBooklet.next_number + toma - 1 <= TicketBooklet.last_number,
            )
            .values(next_number=esperado + toma)
        )
        if resultado.rowcount != 1:
            fallos += 1
            if fallos >= MAX_REINTENTOS_RESERVA:
                raise TalonarioError(
                    "Hubo mucha actividad al reservar los números. Intenta de nuevo."
                )
            continue

        for numero in range(esperado, esperado + toma):
            reservados.append((bloque, numero))
        pendiente -= toma

    return reservados


def _tiene_talonarios(category_id):
    return (
        db.session.scalar(
            select(func.count(TicketBooklet.id)).where(
                TicketBooklet.ticket_category_id == category_id
            )
        )
        > 0
    )


# --------------------------------------------------------------------------
# Números dañados / anulados antes de venderse
# --------------------------------------------------------------------------

def anular_numeros(category_id, cantidad, motivo, usuario):
    """Marca como anulados los siguientes `cantidad` números del talonario
    (boleto dañado, mal impreso, saltado). Consume los números sin sumar
    a la caja."""
    from app.services.cierres_service import dia_cerrado

    categoria = db.session.get(TicketCategory, category_id)
    if categoria is None:
        raise TalonarioError("La categoría elegida no existe.")

    try:
        cantidad = parsear_entero(cantidad, "La cantidad", 1, MAX_ANULAR_DE_UNA_VEZ)
    except ErrorValidacion as error:
        raise TalonarioError(str(error))

    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise TalonarioError("Escribe el motivo (mínimo 5 caracteres): por ejemplo «boleto roto al cortar».")

    if dia_cerrado(datetime.now().date()):
        raise TalonarioError(
            "El día de hoy ya está cerrado. Un administrador debe reabrir el cierre primero."
        )

    try:
        reservados = reservar_numeros(categoria, cantidad)
        for bloque, numero in reservados:
            db.session.add(
                BookletVoid(
                    booklet_id=bloque.id,
                    number=numero,
                    reason=motivo[:200],
                    voided_by=usuario.id,
                )
            )
        numeros = ", ".join(formatear_numero_boleto(n) for _, n in reservados)
        audit_service.registrar(
            "talonario.anular_numero",
            entidad="ticket_booklet",
            entidad_id=reservados[0][0].id,
            detalle=f"{categoria.name}: {numeros}; motivo: {motivo}",
            usuario=usuario,
        )
        db.session.commit()
    except TalonarioError:
        db.session.rollback()
        raise
    return reservados


# --------------------------------------------------------------------------
# Detalle de un talonario
# --------------------------------------------------------------------------

def ventas_del_talonario(booklet_id, limite=30):
    """Últimas ventas que usaron el talonario, con su rango de números."""
    from app.models import Sale, SaleItem

    filas = db.session.execute(
        select(
            Sale.id,
            Sale.created_at,
            Sale.status,
            func.min(Ticket.physical_number),
            func.max(Ticket.physical_number),
            func.count(Ticket.id),
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Ticket, Ticket.sale_item_id == SaleItem.id)
        .where(Ticket.booklet_id == booklet_id)
        .group_by(Sale.id, Sale.created_at, Sale.status)
        .order_by(Sale.created_at.desc())
        .limit(limite)
    ).all()
    return [
        {
            "sale_id": f[0],
            "fecha": f[1],
            "anulada": f[2] == "VOIDED",
            "desde": f[3],
            "hasta": f[4],
            "cantidad": f[5],
        }
        for f in filas
    ]
