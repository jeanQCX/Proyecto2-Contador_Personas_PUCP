#!/usr/bin/env python3
# uart_test.py Generador de aforo falso + envio UART
#
# Conexion fisica (Pi4 ? ESP32):
#   GPIO 14 / pin fisico 8  -> TX Pi ? RX ESP32
#   GPIO 15 / pin fisico 10 -> RX Pi ? TX ESP32
#   GND     / pin fisico 6  -> GND ESP32
#
# Uso:
#   python3 uart_test.py                  # /dev/ttyS0 a 115200
#   python3 uart_test.py /dev/ttyAMA0
#   python3 uart_test.py /dev/ttyS0 9600
 
import serial   # pyserial manejo del puerto UART. pip install pyserial
import time
import random
import sys
import signal
 
PORT        = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
BAUDRATE    = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
INTERVALO_S = 1 #segundos
 
estado = {
    "personas_in":   0,
    "personas_out":  0,
    "vehiculos_in":  0,
    "vehiculos_out": 0,
}
 
running = True
 
def handle_signal(sig, frame):
    global running
    print("\n[!] Serial recibida, cerrando...")
    running = False
 
signal.signal(signal.SIGINT,  handle_signal)
signal.signal(signal.SIGTERM, handle_signal)
 
 
def tick_simulacion():
    # Tirar 4 dados cada uno es el delta de ese flujo para este frame
    p_in_delta  = 1 if random.random() < 0.50 else 0
    p_out_delta = 1 if random.random() < 0.30 else 0
    v_in_delta  = 1 if random.random() < 0.25 else 0
    v_out_delta = 1 if random.random() < 0.55 else 0
 
    estado["personas_in"]  += p_in_delta
    estado["personas_out"] += p_out_delta
    estado["vehiculos_in"]  += v_in_delta
    estado["vehiculos_out"] += v_out_delta
 
    p_aforo = estado["personas_in"]  - estado["personas_out"]
    v_aforo = estado["vehiculos_in"] - estado["vehiculos_out"]
 
    # -- Los 12 valores del protocolo edita aqui para probar valores fijos ---
    v1  = estado["personas_in"]
    v2  = estado["personas_out"]
    v3  = p_aforo
    v4  = p_in_delta
    v5  = p_out_delta
    v6  = p_in_delta - p_out_delta
    v7  = estado["vehiculos_in"]
    v8  = estado["vehiculos_out"]
    v9  = v_aforo
    v10 = v_in_delta
    v11 = v_out_delta
    v12 = v_in_delta - v_out_delta
 
    return (v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12)
    
def enviar(ser, texto):
    ser.write(texto.encode())  # encode() convierte string a bytes UART solo maneja bytes
 
def enviar_estado(ser, msg):
    enviar(ser, f"${msg}\n")
    print(f"  TX -> ${msg.strip()}")
 
def enviar_datos(ser, vals):
    trama = "#" + ",".join(str(v) for v in vals) + "\n"
    enviar(ser, trama)
 
 
def main():
    print(f"Abriendo UART: {PORT} @ {BAUDRATE} baudios")
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1)
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir {PORT}: {e}")
        print("        Habilitaste UART en raspi-config?")
        sys.exit(1)
 
    time.sleep(0.2)
    print(f"Puerto abierto OK\n")
 
    print("[arranque]")
    enviar_estado(ser, "CARGANDO")
    time.sleep(3)
    enviar_estado(ser, "LISTO")
    print()
 
    print(f"Enviando tramas cada {INTERVALO_S}s  (Ctrl+C para salir)\n")
    print(f"{'Trama':<8} {'p_in':>8} {'p_out':>8} {'p_aforo':>8}  "
          f"{'v_in':>8} {'v_out':>8} {'v_aforo':>8}  {'TX->':>4}")
    print("-" * 100)
 
    trama_n = 0
    while running:
        vals = tick_simulacion()
        p_in, p_out, p_aforo = vals[0], vals[1], vals[2]
        v_in, v_out, v_aforo = vals[6], vals[7], vals[8]
 
        trama_n += 1
        raw = "#" + ",".join(str(v) for v in vals)
        print(f"{trama_n:<8} {p_in:>6} {p_out:>8} {p_aforo:>7}  "
              f"{v_in:>10} {v_out:>8} {v_aforo:>10}  {raw:<5}")
 
        enviar_datos(ser, vals)
        time.sleep(INTERVALO_S)
 
    print("\n[fin] Cerrando puerto...")
    ser.close()
    print("Listo.")
 
 
if __name__ == "__main__":
    main()
