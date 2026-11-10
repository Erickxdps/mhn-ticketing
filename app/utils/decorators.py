from functools import wraps

from flask import abort, current_app
from flask_login import current_user


def roles_required(*roles):
    """Restringe una vista a los roles indicados.

    - Sin sesión: se delega en Flask-Login (redirige al login para
      páginas, o responde 401 en JSON para llamadas AJAX; ver
      respuesta_no_autenticado en app/__init__.py).
    - Con sesión pero rol no permitido: 403.

    Uso:
        @roles_required("ADMIN")
        @roles_required("ADMIN", "SELLER")
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator
