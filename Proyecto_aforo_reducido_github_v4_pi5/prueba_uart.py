#!/usr/bin/env python3
# uart_test.py - Generador de aforo falso + envio UART
#
# Conexion fisica (Pi4 -> ESP32):
#   GPIO 14 / pin fisico 8  -> TX Pi -> RX ESP32
#   GPIO 15 / pin fisico 10 -> RX Pi -> TX ESP32
#   GND     / pin fisico 6  -> GND ESP32
#
# Uso:
#   python3 uart_test.py                   # /dev/ttyS0 a 115200
#   python3 uart_test.py /dev/ttyAMA0
#   python3 uart_test.py /dev/ttyS0 9600
 
import serial   # pyserial - pip install pyserial
import time
import random
import sys
import signal
 
PORT           = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
BAUDRATE       = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
TICK_S         = 1   # frecuencia del dado (segundos)
INTERVALO_UART = 15  # cada cuantos ticks se envia por UART
 
# Acumuladores globales - solo crecen, nunca se resetean
estado = {
    "personas_in":   0,
    "personas_out":  0,
    "vehiculos_in":  0,
    "vehiculos_out": 0,
}
 
running = True
 
def handle_signal(sig, frame):
    global running
    print("\n[!] Senal recibida, cerrando...")
    running = False
 
signal.signal(signal.SIGINT,  handle_signal)
signal.signal(signal.SIGTERM, handle_signal)
 
 
def tick_dados():
    """
    Se llama cada segundo. Tira los dados y acumula sobre el estado global.
    Retorna los deltas de este tick y los aforos actuales (6 valores).
 
    Los acumuladores en 'estado' son los que se envian por UART,
    nunca se resetean, solo crecen con cada tick.
    """
    p_in_delta  = 1 if random.random() < 0.20 else 0
    p_out_delta = 1 if random.random() < 0.20 else 0
    v_in_delta  = 1 if random.random() < 0.20 else 0
    v_out_delta = 1 if random.random() < 0.20 else 0
 
    estado["personas_in"]   += p_in_delta
    estado["personas_out"]  += p_out_delta
    estado["vehiculos_in"]  += v_in_delta
    estado["vehiculos_out"] += v_out_delta
 
    # Aforo = cuantos estan adentro ahora
    p_aforo = estado["personas_in"]  - estado["personas_out"]
    v_aforo = estado["vehiculos_in"] - estado["vehiculos_out"]
 
    return (p_in_delta, p_out_delta, p_aforo,
            v_in_delta, v_out_delta, v_aforo)
  
def enviar(ser, texto):
    """Convierte string a bytes y escribe al puerto serie."""
    ser.write(texto.encode())
 
def enviar_estado(ser, msg):
    enviar(ser, f"${msg}\n")
    print(f"  TX -> ${msg.strip()}")
 
def enviar_datos(ser):
    """
    Arma la trama con los acumuladores actuales del estado global.
    Formato: #p_in,p_out,p_aforo,v_in,v_out,v_aforo
    Estos valores son los totales historicos acumulados desde el arranque.
    """
    p_aforo = estado["personas_in"]  - estado["personas_out"]
    v_aforo = estado["vehiculos_in"] - estado["vehiculos_out"]
 
    vals = (
        estado["personas_in"],
        estado["personas_out"],
        p_aforo,
        estado["vehiculos_in"],
        estado["vehiculos_out"],
        v_aforo,
    )
    trama = "#" + ",".join(str(v) for v in vals) + "\n"
    enviar(ser, trama)
    return vals
 
 
def main():
    print(f"Abriendo UART: {PORT} @ {BAUDRATE} baudios")
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1)
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir {PORT}: {e}")
        print("        Habilitaste UART en raspi-config?")
        sys.exit(1)
 
    time.sleep(0.2)
    print("Puerto abierto OK\n")
 
    print("[arranque]")
    enviar_estado(ser, "CARGANDO")
    time.sleep(3)
    enviar_estado(ser, "LISTO")
    print()
 
    # Cabecera consola - dos filas: tick por tick y envios UART
    print(f"Tick cada {TICK_S}s | UART cada {INTERVALO_UART}s  (Ctrl+C para salir)\n")
    print(f"{'tick':<6} {'p_dIn':>6} {'p_dOut':>7} {'p_aforo':>8}   "
          f"{'v_dIn':>6} {'v_dOut':>7} {'v_aforo':>8}   {'UART':>5}")
    print("-" * 72)
 
    tick_n = 0
    while running:
        vals = tick_dados()
        p_din, p_dout, p_aforo, v_din, v_dout, v_aforo = vals
 
        tick_n += 1
 
        # Decidimos si este tick toca envio UART
        es_envio = (tick_n % INTERVALO_UART == 0)
 
        if es_envio:
            uart_vals = enviar_datos(ser)
            # Construimos el string de la trama para mostrarlo en consola
            raw = "#" + ",".join(str(v) for v in uart_vals)
            marca_uart = f"<- {raw}"
        else:
            marca_uart = ""
 
        print(f"{tick_n:<6} {p_din:>6} {p_dout:>7} {p_aforo:>8}   "
              f"{v_din:>6} {v_dout:>7} {v_aforo:>8}   {marca_uart}")
 
        time.sleep(TICK_S)
 
    print("\n[fin] Cerrando puerto...")
    ser.close()
    print("Listo.")
 
 
if __name__ == "__main__":
    main()
 
