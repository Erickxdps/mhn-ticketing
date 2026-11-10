"""Actualizador de base de datos, idempotente y con respaldo previo.

Sirve para dos casos con el mismo comando (`flask upgrade-db`):

1. Instalación nueva: crea todas las tablas, ajustes y categorías.
2. Instalación existente (versión anterior): agrega SOLO lo que falta
   —tablas nuevas, columnas nuevas, índices— sin tocar ni perder datos.
   Si ya está al día, no hace nada (se puede ejecutar cuantas veces se
   quiera; `iniciar_servidor.bat` lo ejecuta en cada arranque).

Antes de modificar una base con datos hace un respaldo verificado.
"""

import os

from sqlalchemy import func, inspect, select, text, update

from app.extensions import db
from app.models import AppSetting, DailyClosure, TicketCategory
from app.services import audit_service, settings_service

CATEGORIAS_BASE = [
    ("Mayores", "5.00"),
    ("Menores", "3.00"),
    ("Extranjeros", "12.00"),
    ("Tercera edad", "2.00"),
    ("Cortesía", "2.00"),
]

# Nombres de la versión anterior que equivalen a las categorías actuales.
RENOMBRES_LEGADOS = {
    "Adulto": "Mayores",
    "Niño": "Menores",
    "Extranjero": "Extranjeros",
}

MARCA_CATEGORIAS = "seed_categories_v1"


def _pendientes_estructura(inspector):
    """Devuelve (tablas, columnas, indices) que faltan respecto a los modelos."""
    existentes = set(inspector.get_table_names())
    tablas, columnas, indices = [], [], []
    for tabla in db.metadata.sorted_tables:
        if tabla.name not in existentes:
            tablas.append(tabla.name)
            continue
        columnas_bd = {c["name"] for c in inspector.get_columns(tabla.name)}
        for columna in tabla.columns:
            if columna.name not in columnas_bd:
                columnas.append((tabla, columna))
        nombres_indices = {i["name"] for i in inspector.get_indexes(tabla.name)}
        for indice in tabla.indexes:
            if indice.name not in nombres_indices:
                indices.append(indice)
    return tablas, columnas, indices


def _sql_agregar_columna(dialecto, tabla, columna):
    q = dialecto.identifier_preparer.quote
    partes = [
        f"ALTER TABLE {q(tabla.name)} ADD COLUMN {q(columna.name)}",
        columna.type.compile(dialect=dialecto),
    ]
    if columna.server_default is not None:
        arg = columna.server_default.arg
        if hasattr(arg, "text"):
            valor = arg.text
        else:
            valor = "'" + str(arg).replace("'", "''") + "'"
        partes.append(f"DEFAULT {valor}")
    if not columna.nullable:
        partes.append("NOT NULL")
    for fk in columna.foreign_keys:
        partes.append(
            f"REFERENCES {q(fk.column.table.name)} ({q(fk.column.name)})"
        )
    return " ".join(partes)


def hay_pendientes():
    """True si faltan tablas, columnas, índices o ajustes por defecto."""
    inspector = inspect(db.engine)
    tablas, columnas, indices = _pendientes_estructura(inspector)
    if tablas or columnas or indices:
        return True
    existentes = {s for (s,) in db.session.execute(select(AppSetting.key))}
    if any(k not in existentes for k in settings_service.DEFAULTS):
        return True
    return MARCA_CATEGORIAS not in existentes


def actualizar_base_de_datos(respaldo=True):
    """Aplica lo que falte. Devuelve la lista de acciones realizadas
    (vacía si ya estaba al día)."""
    acciones = []
    inspector = inspect(db.engine)
    tablas, columnas, indices = _pendientes_estructura(inspector)
    estructura_pendiente = bool(tablas or columnas or indices)
    base_con_datos = "users" in inspector.get_table_names()

    # 1) Respaldo previo (solo SQLite, solo si hay datos que proteger)
    if respaldo and estructura_pendiente and base_con_datos:
        ruta = db.engine.url.database if db.engine.url.get_backend_name() == "sqlite" else None
        if ruta and os.path.exists(ruta):
            from backup_db import crear_respaldo

            copia = crear_respaldo(prefijo="pre_actualizacion", origen=ruta)
            acciones.append(f"Respaldo previo creado: {copia}")

    # 2) Tablas nuevas (y sus índices)
    if tablas:
        db.create_all()
        acciones.append("Tablas creadas: " + ", ".join(tablas))

    # 3) Columnas nuevas en tablas existentes
    columnas_cierres_nuevas = False
    for tabla, columna in columnas:
        with db.engine.begin() as conexion:
            conexion.execute(text(_sql_agregar_columna(db.engine.dialect, tabla, columna)))
        acciones.append(f"Columna agregada: {tabla.name}.{columna.name}")
        if tabla.name == "daily_closures" and columna.name == "total_cash":
            columnas_cierres_nuevas = True

    # 4) Índices que faltan en tablas existentes
    for indice in indices:
        if indice.table.name in tablas:
            continue  # ya los creó create_all
        indice.create(bind=db.engine, checkfirst=True)
        acciones.append(f"Índice creado: {indice.name}")

    # 5) Cierres anteriores: completar el desglose efectivo/QR con las ventas reales
    if columnas_cierres_nuevas:
        for metodo, columna in (("CASH", "total_cash"), ("QR", "total_qr")):
            db.session.execute(
                text(
                    f"UPDATE daily_closures SET {columna} = COALESCE(("
                    "SELECT SUM(s.total_amount) FROM sales s "
                    "WHERE s.payment_method = :metodo "
                    "AND date(s.created_at) = daily_closures.closure_date), 0)"
                ),
                {"metodo": metodo},
            )
        db.session.commit()
        acciones.append("Cierres anteriores: desglose efectivo/QR calculado desde las ventas.")

    # 6) Ajustes por defecto
    existentes = {s for (s,) in db.session.execute(select(AppSetting.key))}
    for clave, valor in settings_service.DEFAULTS.items():
        if clave not in existentes:
            db.session.add(AppSetting(key=clave, value=valor))
            acciones.append(f"Ajuste creado: {clave} = {valor}")
    db.session.commit()

    # 7) Categorías base (una sola vez)
    if MARCA_CATEGORIAS not in existentes:
        acciones.extend(_asegurar_categorias_base())
        db.session.add(AppSetting(key=MARCA_CATEGORIAS, value="1"))
        db.session.commit()

    if acciones:
        audit_service.registrar(
            "sistema.actualizar_bd",
            entidad="sistema",
            detalle=" | ".join(acciones)[:1900],
            commit=True,
        )
    return acciones


def _asegurar_categorias_base():
    """Deja las cinco categorías vigentes. Si existen las de la versión
    anterior (Adulto, Niño, Extranjero) se renombran conservando su
    historial y su precio actual; las que falten se crean con el precio
    base. Los precios de categorías ya existentes NO se modifican."""
    acciones = []
    existentes = {c.name.lower(): c for c in db.session.scalars(select(TicketCategory))}
    for nombre, precio in CATEGORIAS_BASE:
        if nombre.lower() in existentes:
            continue
        for viejo, nuevo in RENOMBRES_LEGADOS.items():
            if nuevo == nombre and viejo.lower() in existentes:
                categoria = existentes.pop(viejo.lower())
                categoria.name = nombre
                existentes[nombre.lower()] = categoria
                acciones.append(
                    f"Categoría renombrada: {viejo} -> {nombre} (precio actual: Bs {categoria.price}; "
                    "revísalo en Categorías)"
                )
                break
        else:
            categoria = TicketCategory(name=nombre, price=precio, is_active=True)
            db.session.add(categoria)
            existentes[nombre.lower()] = categoria
            acciones.append(f"Categoría creada: {nombre} (Bs {precio})")
    return acciones
