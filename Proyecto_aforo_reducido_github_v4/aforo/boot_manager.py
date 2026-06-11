import RPi.GPIO as GPIO
import time
import subprocess
import sys
import os
    
# ---------------------------------------------
# PINES
# ---------------------------------------------
PIN_BOTON = 27
PIN_LED   = 24

# Rutas de los servicios
SERVICES_DIR   = "/home/pi/proyecto_aforo/services"
SYSTEMD_DIR    = "/etc/systemd/system"

# ---------------------------------------------
# CONFIGURACION GPIO
# ---------------------------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_BOTON, GPIO.IN,  pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_LED,   GPIO.OUT, initial=GPIO.LOW)

# ---------------------------------------------
# FUNCIONES
# ---------------------------------------------

def led(estado):
    GPIO.output(PIN_LED, GPIO.HIGH if estado else GPIO.LOW)

def instalar_servicios(lista):
    """
    Copia los archivos .service indicados desde la carpeta del proyecto
    hacia /etc/systemd/system/ para que systemd los reconozca.
    El daemon-reload se hace en arrancar_modo1/2 despues de copiar,
    no aqui, para evitar que systemd recargue aforo-boot mientras corre.
    """
    for nombre in lista:
        origen  = os.path.join(SERVICES_DIR, nombre)
        destino = os.path.join(SYSTEMD_DIR,  nombre)
        subprocess.run(["cp", origen, destino])
        print(f"  [boot] {nombre} instalado.")

def desinstalar_servicios(lista):
    """
    Borra los archivos .service indicados de /etc/systemd/system/.
    Los archivos originales siguen en la carpeta del proyecto.
    Hace daemon-reload al final para que systemd olvide los servicios.
    Aqui si es seguro hacer reload porque aforo-boot ya termino.
    """
    for nombre in lista:
        destino = os.path.join(SYSTEMD_DIR, nombre)
        if os.path.exists(destino):
            os.remove(destino)
            print(f"  [boot] {nombre} desinstalado.")
    subprocess.run(["systemctl", "daemon-reload"])

def arrancar_modo2():
    """
    Instala y arranca el motor de aforo (Modo 2).
    El daemon-reload se hace con delay en hilo separado
    para que aforo-boot termine antes del reload.
    """
    import threading
    print("  [boot] Arrancando Modo 2...")
    #Comentar para no comenzar con modo 2
    #instalar_servicios(["aforo-engine.service"])

    def reload_y_arrancar():
        import time
        time.sleep(2)  # esperar a que aforo-boot termine
        subprocess.run(["systemctl", "daemon-reload"])
        subprocess.run(["systemctl", "start", "aforo-engine.service"])
        print("  [boot] Modo 2 activo.")

    threading.Thread(target=reload_y_arrancar).start()

def arrancar_modo1():
    """
    Instala y arranca todos los servicios del Modo 1 en orden:
    1. hostapd     -> crea la red WiFi AP
    2. wlan-static -> asigna IP fija 192.168.4.1 a wlan0
    3. dnsmasq     -> asigna IPs a clientes conectados al AP
    4. aforo-web   -> levanta el servidor Flask de configuracion
    """
    import threading
    print("  [boot] Arrancando Modo 1...")
    instalar_servicios(["wlan-static-ip.service", "aforo-web.service"])

    def reload_y_arrancar():
        import time
        time.sleep(2)  # esperar a que aforo-boot termine
        subprocess.run(["systemctl", "daemon-reload"])
        subprocess.run(["systemctl", "start", "hostapd.service"])
        time.sleep(3)
        subprocess.run(["systemctl", "start", "wlan-static-ip.service"])
        subprocess.run(["systemctl", "start", "dnsmasq.service"])
        subprocess.run(["systemctl", "start", "aforo-web.service"])
        print("  [boot] Modo 1 activo.")

    threading.Thread(target=reload_y_arrancar).start()
    
# ---------------------------------------------
# VENTANA DE CONFIGURACION
# ---------------------------------------------

def ventana_config():
    print("  [boot] Ventana de configuracion abierta (5 segundos)...")

    duracion     = 5.0
    intervalo    = 0.25
    transcurrido = 0.0
    estado_led   = False

    while transcurrido < duracion:
        estado_led = not estado_led
        led(estado_led)

        pasos = 10
        for _ in range(pasos):
            time.sleep(intervalo / pasos)
            if GPIO.input(PIN_BOTON) == GPIO.LOW:
                print("  [boot] Boton presionado, entrando a Modo 1.")
                led(False)
                return True

        transcurrido += intervalo

    led(False)
    print("  [boot] Ventana cerrada sin presionar boton, entrando a Modo 2.")
    return False

# ---------------------------------------------
# MAIN
# ---------------------------------------------

def main():
    entrar_config = False
    try:
        entrar_config = ventana_config()

        if entrar_config:
            led(True)          # encender constante
            arrancar_modo1()   # arrancar Flask
            # sin cleanup, Flask hereda el pin en HIGH

        else:
            led(False)
            GPIO.cleanup()
            arrancar_modo2()

    except KeyboardInterrupt:
        print("  [boot] Interrumpido.")
        GPIO.cleanup()

if __name__ == "__main__":
    main()
