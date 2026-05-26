import os
import sys
import cv2
import threading
from flask import Flask, jsonify, request, render_template, send_file
import io
import subprocess

# CONTROL de LED azul -> apagar
import RPi.GPIO as GPIO

PIN_LED = 24
# Inicializar GPIO para el LED
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_LED, GPIO.OUT, initial=GPIO.LOW)

# Encender LED al arrancar Flask en Modo 1
#evita que el led se apague por condiciones de carrera
try:
    GPIO.output(PIN_LED, GPIO.HIGH)
except:
    pass

# Agregar el directorio padre al path para importar config_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_manager import ConfigManager

app = Flask(__name__)
cfg = ConfigManager()

# ---------------------------------------------
# CAMARA
# ---------------------------------------------

def capturar_frame():
    camara_cfg = cfg.get("camara", {})
    indice     = camara_cfg.get("indice", 0)

    cap = cv2.VideoCapture(indice)

    # Descartar frames iniciales para dar tiempo a la camara de estabilizarse
    # La mayoria de camaras necesitan entre 10-20 frames para estabilizar
    # la exposicion y el balance de blancos
    frames_descarte = 15
    for _ in range(frames_descarte):
        cap.read()  # leer y descartar

    # Capturar el frame bueno
    ret, frame = cap.read()
    cap.release()

    if not ret:
        return None

    _, buffer = cv2.imencode(".jpg", frame)
    return io.BytesIO(buffer.tobytes())

# ---------------------------------------------
# RUTAS
# ---------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/frame")
def frame():
    """
    Captura un frame de la camara y lo devuelve como imagen JPEG.
    El navegador lo muestra en un <img src="/frame">.
    Cada vez que el usuario presiona "Actualizar foto" se llama este endpoint.
    """
    imagen = capturar_frame()
    if imagen is None:
        return jsonify({"error": "No se pudo capturar el frame"}), 500

    return send_file(imagen, mimetype="image/jpeg")
    
    
@app.route("/config")
def get_config():
    """
    Devuelve el config.json completo como JSON.
    La pagina lo usa para mostrar la tabla de configuracion actual.
    """
    return jsonify(cfg.get_todo())


@app.route("/config/set", methods=["POST"])
def set_config():
    """
    Recibe { "clave": "linea_personas", "valor": {"p1": [x1,y1], "p2": [x2,y2]} }
    y lo guarda via ConfigManager.
    """
    data = request.get_json()
    clave = data.get("clave")
    valor = data.get("valor")

    if not clave or valor is None:
        return jsonify({"error": "Faltan clave o valor"}), 400

    cfg.set(clave, valor)
    return jsonify({"ok": True, "clave": clave, "valor": valor})


@app.route("/config/reset", methods=["POST"])
def reset_config():
    """
    Recibe { "clave": "linea_personas" } para resetear una clave,
    o { "todo": true } para resetear todo al template.
    """
    data = request.get_json()

    if data.get("todo"):
        cfg.reset_todo()
        return jsonify({"ok": True, "mensaje": "Config reseteada al template."})

    clave = data.get("clave")
    if not clave:
        return jsonify({"error": "Falta clave"}), 400

    cfg.reset(clave)
    return jsonify({"ok": True, "clave": clave})


def aplicar_config_red():
    """
    Lee ssid y password del config.json y los escribe en hostapd.conf.
    Luego reinicia hostapd para aplicar los cambios.
    """
    red = cfg.get("red", {})
    ssid     = red.get("ssid",     "aforo-config")
    password = red.get("password", "12345678")

    config_hostapd = f"""interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
    with open("/etc/hostapd/hostapd.conf", "w") as f:
        f.write(config_hostapd)

    subprocess.run(["systemctl", "restart", "hostapd"], check=True)
    print("  [Red] hostapd reiniciado con nuevos datos.")


@app.route("/finalizar", methods=["POST"])
def finalizar():
    linea_per = cfg.get("linea_personas")
    linea_veh = cfg.get("linea_vehiculos")
    roi       = cfg.get("roi")

    if not linea_per or linea_per.get("p1") is None:
        return jsonify({"error": "Linea de personas no configurada."}), 400
    if not linea_veh or linea_veh.get("p1") is None:
        return jsonify({"error": "Linea de vehiculos no configurada."}), 400
    if not roi or roi.get("p1") is None:
        return jsonify({"error": "ROI no configurado."}), 400

    def apagar():
        import time
        import os
        time.sleep(1)

        try:
            GPIO.output(PIN_LED, GPIO.LOW)
            GPIO.cleanup()
            print("  [GPIO] LED apagado.")
        except Exception as e:
            print(f"  [GPIO] Error apagando LED: {e}")

        try:
            aplicar_config_red()
        except Exception as e:
            print(f"  [Red] Error: {e}")

        subprocess.run(["systemctl", "stop", "dnsmasq.service"])
        subprocess.run(["systemctl", "stop", "wlan-static-ip.service"])
        subprocess.run(["systemctl", "stop", "hostapd.service"])

        for nombre in ["wlan-static-ip.service", "aforo-web.service"]:
            destino = f"/etc/systemd/system/{nombre}"
            if os.path.exists(destino):
                os.remove(destino)

        subprocess.run(["systemctl", "daemon-reload"])
        print("  Modo 1 completamente apagado.")
        subprocess.run(["reboot"])

    threading.Thread(target=apagar).start()
    return jsonify({"ok": True, "mensaje": "Configuracion finalizada. Cerrando sistema."})

# ---------------------------------------------
# ARRANQUE
# ---------------------------------------------

if __name__ == "__main__":
    # host="0.0.0.0" para que sea accesible desde otros dispositivos en la red
    # port=80 para que el usuario solo tenga que escribir la IP sin puerto
    app.run(host="0.0.0.0", port=80, debug=False)
