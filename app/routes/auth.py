from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User
from app.security import destino_seguro, limitador_login, validar_password
from app.services import audit_service

auth_bp = Blueprint("auth", __name__)

# Se compara contra este hash cuando el usuario no existe, para que
# responder "usuario inexistente" no sea más rápido que "clave incorrecta".
_HASH_FALSO = generate_password_hash("contraseña-inexistente")


def _siguiente():
    candidato = request.form.get("next") or request.args.get("next")
    return candidato if destino_seguro(candidato) else None


@auth_bp.route("/login", methods=["GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    return render_template("auth/login.html", siguiente=_siguiente() or "")


@auth_bp.route("/login", methods=["POST"])
def login_post():
    username = request.form.get("username", "").strip()[:80]
    password = request.form.get("password", "")[:200]
    ip = request.remote_addr or "desconocida"
    siguiente = _siguiente()

    espera = limitador_login.segundos_bloqueado(username, ip)
    if espera:
        minutos = max(1, round(espera / 60))
        current_app.logger.warning(
            f"Login bloqueado — usuario intentado: '{username}' ip={ip} espera={espera}s"
        )
        flash(
            f"Demasiados intentos fallidos. Espera {minutos} minuto{'s' if minutos != 1 else ''} "
            "antes de volver a intentarlo.",
            "danger",
        )
        return redirect(url_for("auth.login", next=siguiente))

    user = User.query.filter_by(username=username).first()

    # Mensaje genérico: no se distingue entre "no existe", "contraseña
    # incorrecta" o "usuario inactivo" para no filtrar información.
    if user is None:
        check_password_hash(_HASH_FALSO, password)
        credenciales_validas = False
    else:
        credenciales_validas = user.check_password(password) and user.is_active

    if not credenciales_validas:
        bloqueado = limitador_login.registrar_fallo(username, ip)
        current_app.logger.warning(
            f"Login fallido — usuario intentado: '{username}' ip={ip}"
        )
        if bloqueado:
            audit_service.registrar(
                "login.bloqueo",
                entidad="user",
                detalle=f"Bloqueo temporal por intentos fallidos: '{username}' desde {ip}",
                commit=True,
            )
            flash(
                "Demasiados intentos fallidos. Espera unos minutos antes de volver a intentarlo.",
                "danger",
            )
        else:
            flash("Usuario o contraseña incorrectos, o usuario inactivo.", "danger")
        return redirect(url_for("auth.login", next=siguiente))

    limitador_login.registrar_exito(username, ip)
    # Sesión nueva al iniciar: evita reutilizar una sesión anterior.
    session.clear()
    recordar = request.form.get("remember") == "on"
    login_user(user, remember=recordar)
    current_app.logger.info(f"Login exitoso — usuario={user.username} rol={user.role} ip={ip}")
    flash(f"Bienvenido/a, {user.full_name}.", "success")
    return redirect(siguiente or url_for("main.index"))


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/perfil/password", methods=["GET"])
@login_required
def cambiar_password():
    return render_template("auth/change_password.html")


@auth_bp.route("/perfil/password", methods=["POST"])
@login_required
def cambiar_password_post():
    actual = request.form.get("password_actual", "")
    nueva = request.form.get("password_nueva", "")
    confirmacion = request.form.get("password_confirmacion", "")

    if not current_user.check_password(actual):
        flash("La contraseña actual es incorrecta.", "danger")
        return redirect(url_for("auth.cambiar_password"))

    error = validar_password(nueva, current_user.username)
    if error:
        flash(error, "danger")
        return redirect(url_for("auth.cambiar_password"))

    if nueva == actual:
        flash("La nueva contraseña debe ser distinta de la actual.", "danger")
        return redirect(url_for("auth.cambiar_password"))

    if nueva != confirmacion:
        flash("La confirmación no coincide con la nueva contraseña.", "danger")
        return redirect(url_for("auth.cambiar_password"))

    current_user.set_password(nueva)
    audit_service.registrar(
        "usuario.cambiar_password_propia",
        entidad="user",
        entidad_id=current_user.id,
        detalle=f"{current_user.username} cambió su contraseña",
    )
    db.session.commit()
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("main.index"))
