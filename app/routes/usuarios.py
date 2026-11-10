import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.user import USER_ROLES, User
from app.security import validar_password
from app.services import audit_service
from app.utils.decorators import roles_required

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

PATRON_USUARIO = re.compile(r"^[A-Za-z0-9._-]{3,40}$")


def _admins_activos_restantes(excluir_user_id=None):
    """Cuenta cuántos ADMIN activos quedarían, excluyendo opcionalmente
    al usuario que se está editando (para evaluar el cambio antes de
    aplicarlo)."""
    query = User.query.filter_by(role="ADMIN", is_active=True)
    if excluir_user_id is not None:
        query = query.filter(User.id != excluir_user_id)
    return query.count()


@usuarios_bp.route("", methods=["GET"])
@roles_required("ADMIN")
def listar():
    usuarios = User.query.order_by(User.username).all()
    return render_template("usuarios/list.html", usuarios=usuarios)


@usuarios_bp.route("/nuevo", methods=["GET"])
@roles_required("ADMIN")
def nuevo():
    return render_template(
        "usuarios/form.html", usuario=None, roles=USER_ROLES, modo="nuevo", datos={}
    )


@usuarios_bp.route("/nuevo", methods=["POST"])
@roles_required("ADMIN")
def nuevo_post():
    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "")
    password = request.form.get("password", "")
    is_active = request.form.get("is_active") == "on"

    errores = []
    if not PATRON_USUARIO.match(username):
        errores.append(
            "El usuario debe tener entre 3 y 40 caracteres: letras, números, punto, guion o guion bajo."
        )
    elif User.query.filter(db.func.lower(User.username) == username.lower()).first():
        errores.append(f"Ya existe un usuario con username '{username}'.")
    if not full_name or len(full_name) > 150:
        errores.append("El nombre completo es obligatorio (máximo 150 caracteres).")
    if role not in USER_ROLES:
        errores.append("Rol inválido.")
    error_password = validar_password(password, username)
    if error_password:
        errores.append(error_password)

    if errores:
        for error in errores:
            flash(error, "danger")
        return render_template(
            "usuarios/form.html",
            usuario=None,
            roles=USER_ROLES,
            modo="nuevo",
            datos={"username": username, "full_name": full_name, "role": role, "is_active": is_active},
        )

    nuevo_usuario = User(
        username=username, full_name=full_name, role=role, is_active=is_active
    )
    nuevo_usuario.set_password(password)
    db.session.add(nuevo_usuario)
    db.session.flush()
    audit_service.registrar(
        "usuario.crear",
        entidad="user",
        entidad_id=nuevo_usuario.id,
        detalle=f"{username} ({role}), activo={is_active}",
    )
    db.session.commit()

    flash(f"Usuario '{username}' creado correctamente.", "success")
    return redirect(url_for("usuarios.listar"))


@usuarios_bp.route("/<int:user_id>/editar", methods=["GET"])
@roles_required("ADMIN")
def editar(user_id):
    usuario = db.get_or_404(User, user_id)
    return render_template(
        "usuarios/form.html", usuario=usuario, roles=USER_ROLES, modo="editar", datos={}
    )


@usuarios_bp.route("/<int:user_id>/editar", methods=["POST"])
@roles_required("ADMIN")
def editar_post(user_id):
    usuario = db.get_or_404(User, user_id)

    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "")
    is_active = request.form.get("is_active") == "on"
    nueva_password = request.form.get("password", "")

    errores = []
    if not full_name or len(full_name) > 150:
        errores.append("El nombre completo es obligatorio (máximo 150 caracteres).")
    if role not in USER_ROLES:
        errores.append("Rol inválido.")
    if nueva_password:
        error_password = validar_password(nueva_password, usuario.username)
        if error_password:
            errores.append(error_password)

    # Regla: no permitir que el último ADMIN activo deje de serlo,
    # ya sea por desactivación o por cambio de rol.
    dejaria_de_ser_admin_activo = usuario.role == "ADMIN" and (
        role != "ADMIN" or not is_active
    )
    if dejaria_de_ser_admin_activo and _admins_activos_restantes(excluir_user_id=usuario.id) == 0:
        errores.append(
            "No se puede desactivar ni quitar el rol ADMIN al último administrador activo."
        )

    if errores:
        for error in errores:
            flash(error, "danger")
        return render_template(
            "usuarios/form.html",
            usuario=usuario,
            roles=USER_ROLES,
            modo="editar",
            datos={"full_name": full_name, "role": role, "is_active": is_active},
        )

    cambios = []
    if usuario.full_name != full_name:
        cambios.append(f"nombre: '{usuario.full_name}' -> '{full_name}'")
    if usuario.role != role:
        cambios.append(f"rol: {usuario.role} -> {role}")
    if usuario.is_active != is_active:
        cambios.append(f"activo: {usuario.is_active} -> {is_active}")
    if nueva_password:
        cambios.append("contraseña restablecida")

    usuario.full_name = full_name
    usuario.role = role
    usuario.is_active = is_active
    if nueva_password:
        usuario.set_password(nueva_password)

    if cambios:
        audit_service.registrar(
            "usuario.editar",
            entidad="user",
            entidad_id=usuario.id,
            detalle=f"{usuario.username}: " + "; ".join(cambios),
        )
    db.session.commit()
    flash(f"Usuario '{usuario.username}' actualizado correctamente.", "success")
    return redirect(url_for("usuarios.listar"))
