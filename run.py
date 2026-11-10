import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # host="0.0.0.0" permite que otras computadoras/celulares en la
    # misma red del museo se conecten (no solo esta máquina).
    #
    # debug solo se activa si se define explícitamente FLASK_DEBUG=1
    # en el entorno. Dejarlo en True de forma fija sería un riesgo de
    # seguridad real en un servidor que queda prendido atendiendo a
    # varias personas: el depurador interactivo de Flask permite
    # ejecutar código arbitrario si alguien lo encuentra expuesto en
    # la red.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=8472, debug=debug)
