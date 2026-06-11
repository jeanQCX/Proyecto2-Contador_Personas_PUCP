# main_debug.py
# Gemelo de main.py orientado a desarrollo y validacion.
# Muestra ventana OpenCV con toda la informacion del pipeline:
# ROI, lineas de conteo, p3, bbox, centroides, trayectorias, FPS y conteos.
# NO usar en produccion - solo desarrollo.

# warning wayland----------------------------------------
import os
os.environ["QT_QPA_PLATFORM"] = "xcb"
# -------------------------------------------------------

import time
import math
import threading
import subprocess
import serial
import cv2

from config_manager import ConfigManager
from tracker        import Tracker
from counter        import Counter
from geometry       import linea_desde_config, roi_desde_config

# ---------------------------------------------------------------------------
# Fuente de video - cambiar aqui
# ---------------------------------------------------------------------------
FUENTE = "../Teros_v1c4.mp4"   # path a video
# FUENTE = None                 # None = camara

# ---------------------------------------------------------------------------
# Configuracion UART debug - editar aqui directamente
# ---------------------------------------------------------------------------
UART_ACTIVO    = False           # True = manda por serial, False = solo imprime
UART_PUERTO    = "/dev/ttyS0"   # puerto serie hacia el ESP32
UART_BAUD      = 115200         # velocidad en baudios
UART_INTERVALO = 1.0            # segundos entre tramas

# ---------------------------------------------------------------------------
# Colores BGR para visualizacion
# ---------------------------------------------------------------------------
COLOR_ROI               = (0,   255, 255)   # amarillo
COLOR_LINEA_PERSONAS    = (0,   255, 0  )   # verde
COLOR_LINEA_VEHICULOS   = (255, 0,   0  )   # azul
COLOR_TEXTO             = (255, 255, 255)   # blanco
COLOR_PANEL_BG          = (30,  30,  30 )   # gris oscuro panel
COLOR_EPSILON_PERSONAS  = (50,  255, 50 )   # verde lima
COLOR_EPSILON_VEHICULOS = (255, 200, 100)   # azul claro


def abrir_fuente(cfg: ConfigManager):
    """Abre camara o video segun FUENTE."""
    if FUENTE is not None:
        cap = cv2.VideoCapture(FUENTE)
        if not cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el video: {FUENTE}")
        print(f"  [Debug] Fuente: video {FUENTE}")
    else:
        camara_cfg = cfg.get("camara", {})
        indice     = camara_cfg.get("indice", 0)
        ancho      = camara_cfg.get("ancho",  640)
        alto       = camara_cfg.get("alto",   480)
        cap = cv2.VideoCapture(indice, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  ancho)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
        print(f"  [Debug] Fuente: camara indice {indice}")
    return cap


def dibujar_roi(vis, roi):
    """Dibuja el rectangulo del ROI."""
    if roi is None:
        return
    p1, p2 = roi
    x_min = int(min(p1[0], p2[0])); y_min = int(min(p1[1], p2[1]))
    x_max = int(max(p1[0], p2[0])); y_max = int(max(p1[1], p2[1]))
    cv2.rectangle(vis, (x_min, y_min), (x_max, y_max), COLOR_ROI, 2)
    cv2.putText(vis, "ROI", (x_min + 4, y_min + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_ROI, 2)


def _linea_paralela(p1, p2, offset_px):
    """
    Calcula dos puntos de una linea paralela a p1->p2
    desplazada offset_px pixeles en direccion perpendicular.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    long = math.sqrt(dx*dx + dy*dy)
    if long < 1e-10:
        return p1, p2
    # Vector perpendicular normalizado
    nx = -dy / long
    ny =  dx / long
    q1 = (int(p1[0] + nx * offset_px), int(p1[1] + ny * offset_px))
    q2 = (int(p2[0] + nx * offset_px), int(p2[1] + ny * offset_px))
    return q1, q2


def _linea_punteada(vis, pt1, pt2, color, grosor=1, segmento=8, espacio=6):
    """Dibuja una linea punteada entre pt1 y pt2."""
    dx = pt2[0] - pt1[0]
    dy = pt2[1] - pt1[1]
    long = math.sqrt(dx*dx + dy*dy)
    if long < 1e-10:
        return
    paso = segmento + espacio
    pasos = int(long / paso)
    for i in range(pasos + 1):
        t1 = i * paso / long
        t2 = min((i * paso + segmento) / long, 1.0)
        x1 = int(pt1[0] + dx * t1); y1 = int(pt1[1] + dy * t1)
        x2 = int(pt1[0] + dx * t2); y2 = int(pt1[1] + dy * t2)
        cv2.line(vis, (x1, y1), (x2, y2), color, grosor)


def dibujar_linea(vis, linea, color, color_epsilon, epsilon_px=0):
    """Dibuja la linea de conteo, bandas epsilon punteadas, extremos y p3."""
    if linea is None:
        return
    p1, p2, p3 = linea
    pt1 = (int(p1[0]), int(p1[1]))
    pt2 = (int(p2[0]), int(p2[1]))
    pt3 = (int(p3[0]), int(p3[1]))

    # Bandas epsilon - lineas paralelas punteadas
    if epsilon_px > 0:
        q1p, q2p = _linea_paralela(p1, p2,  epsilon_px)
        q1n, q2n = _linea_paralela(p1, p2, -epsilon_px)
        _linea_punteada(vis, q1p, q2p, color_epsilon, grosor=1)
        _linea_punteada(vis, q1n, q2n, color_epsilon, grosor=1)

    # Linea principal
    cv2.line(vis, pt1, pt2, color, 2)

    # Extremos
    cv2.circle(vis, pt1, 5, color, -1)
    cv2.circle(vis, pt2, 5, color, -1)

    # P3 - zona positiva, mismo color que la linea
    cv2.circle(vis, pt3, 4, color, -1)
    cv2.putText(vis, "p3", (pt3[0] + 6, pt3[1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

def dibujar_panel(vis, conteos):
    """
    Dibuja un panel semitransparente en la esquina superior derecha.
    Cada seccion tiene un cuadradito del color de su clase como leyenda.

    Muestra:
        IN    -- total acumulado que entro (solo sube)
        OUT   -- total acumulado que salio (solo sube)
        AFORO -- cuantos hay adentro ahora (puede bajar o ser negativo)
    """
    h, w = vis.shape[:2]

    # Cada entrada: (texto, color_texto, color_cuadrado_o_None)
    # color_cuadrado no None solo en las cabeceras de seccion
    entradas = [
        ("PERSONAS", COLOR_LINEA_PERSONAS, COLOR_LINEA_PERSONAS),
        (f"  IN:    {conteos['p_acu_in']}",  COLOR_TEXTO, None),
        (f"  OUT:   {conteos['p_acu_out']}", COLOR_TEXTO, None),
        (f"  AFORO: {conteos['p_aforo']}",   COLOR_TEXTO, None),
        ("", None, None),
        ("VEHICULOS", COLOR_LINEA_VEHICULOS, COLOR_LINEA_VEHICULOS),
        (f"  IN:    {conteos['v_acu_in']}",  COLOR_TEXTO, None),
        (f"  OUT:   {conteos['v_acu_out']}", COLOR_TEXTO, None),
        (f"  AFORO: {conteos['v_aforo']}",   COLOR_TEXTO, None),
    ]

    margen      = 5    # espacio entre borde del panel y el texto
    linea_h     = 15   # altura de separacion entre textos
    ancho_panel = 120  # ancho del panel en pixeles
    alto_panel  = len(entradas) * linea_h + margen * 2

    x1 = w - ancho_panel - margen
    y1 = margen
    x2 = w - margen
    y2 = y1 + alto_panel

    # Fondo semitransparente
    overlay = vis.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), COLOR_PANEL_BG, -1)
    cv2.addWeighted(overlay, 0.4, vis, 0.6, 0, vis)

    TAM_CUAD = 8   # lado del cuadradito de leyenda en pixeles

    for i, (texto, color_texto, color_cuad) in enumerate(entradas):
        if not texto:
            continue
        cy = y1 + margen + i * linea_h + 14

        # Cuadradito de color en cabeceras de seccion
        if color_cuad is not None:
            cx1 = x1 + 5
            cy1 = cy - TAM_CUAD + 1
            cv2.rectangle(vis, (cx1, cy1), (cx1 + TAM_CUAD, cy1 + TAM_CUAD), color_cuad, -1)
            offset_texto = cx1 + TAM_CUAD + 4  # texto desplazado a la derecha del cuadrado
        else:
            offset_texto = x1 + 8

        cv2.putText(vis, texto, (offset_texto, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_texto, 1)


def _abrir_uart_debug():
    """
    Intenta abrir el puerto serial si UART_ACTIVO es True.
    Devuelve el objeto serial o None si falla o esta desactivado.
    """
    if not UART_ACTIVO:
        print("  [Debug] UART desactivado (UART_ACTIVO=False), solo imprime en terminal.")
        return None
    try:
        uart = serial.Serial(UART_PUERTO, UART_BAUD, timeout=1)
        print(f"  [Debug] UART activo en {UART_PUERTO} a {UART_BAUD} baud.")
        return uart
    except Exception as e:
        print(f"  [Debug] No se pudo abrir UART ({e}), solo imprime en terminal.")
        return None


def _enviar_o_imprimir(uart, conteos):
    """
    Arma la trama con los 6 conteos, la imprime en terminal
    y si el UART esta activo la manda por serial.

    Formato: #p_acu_in,p_acu_out,p_aforo,v_acu_in,v_acu_out,v_aforo
    """
    trama = (
        f"#{conteos['p_acu_in']},"
        f"{conteos['p_acu_out']},"
        f"{conteos['p_aforo']},"
        f"{conteos['v_acu_in']},"
        f"{conteos['v_acu_out']},"
        f"{conteos['v_aforo']}"
    )
    print(f"  [UART TX] {trama}")

    if uart is not None:
        try:
            uart.write((trama + "\n").encode("ascii"))
        except Exception as e:
            print(f"  [Debug] Error escribiendo UART: {e}")


def _receptor_debug(uart, stop_event):
    """
    Hilo daemon que escucha comandos del ESP32 en modo debug.
    Igual que ReceptorUART de main.py, incluyendo el apagado real del sistema.
    Permite probar el flujo completo desde el ESP32 sin diferencias con main.py.

    Comandos soportados:
        !APAGAR -- cierra el debug y apaga el sistema operativo
    """
    while not stop_event.is_set():
        try:
            linea = uart.readline()
            if linea:
                cmd = linea.decode("ascii", errors="ignore").strip()
                if cmd.startswith("!"):
                    print(f"  [UART RX] Comando recibido: {cmd}")
                    if cmd == "!APAGAR":
                        print("  [UART RX] !APAGAR recibido. Apagando sistema...")
                        stop_event.set()  # detiene este hilo
                        # pequena espera para que el bucle principal salga
                        time.sleep(2)
                        subprocess.run(["sudo", "shutdown", "-h", "now"])
        except Exception as e:
            if not stop_event.is_set():
                print(f"  [Debug] Error leyendo UART: {e}")


def main():
    cfg     = ConfigManager()
    tracker = Tracker(cfg)
    counter = Counter(cfg)

    # Leer lineas y ROI del config para dibujarlas
    linea_personas  = linea_desde_config(cfg.get("linea_personas",  {}))
    linea_vehiculos = linea_desde_config(cfg.get("linea_vehiculos", {}))
    roi             = roi_desde_config(cfg.get("roi", {}))

    # UART debug
    uart       = _abrir_uart_debug()
    stop_event = threading.Event()  # senaliza al hilo receptor que debe parar

    # Arrancar receptor solo si el UART esta disponible
    if uart is not None:
        hilo_rx = threading.Thread(
            target=_receptor_debug, args=(uart, stop_event), daemon=True
        )
        hilo_rx.start()

    cap          = abrir_fuente(cfg)
    t_prev       = time.time()
    t_ult_uart   = time.time()  # control del intervalo de envio

    print(f"  [Debug] ESC para salir, SPACE pausa. Intervalo UART: {UART_INTERVALO}s")

    while True:
        # Chequear si el receptor UART pidio parar (ej: comando !APAGAR)
        if stop_event.is_set():
            break

        ret, frame = cap.read()
        if not ret:
            print("  [Debug] Fin de fuente.")
            break

        # Resize si es video (comentar para camara)
        if FUENTE is not None:
            frame = cv2.resize(frame, (640, 480))

        # Pipeline
        objetos = tracker.trackear(frame)
        counter.actualizar(objetos)
        conteos = counter.get_conteos()

        # Enviar/imprimir UART segun intervalo
        t_now = time.time()
        if t_now - t_ult_uart >= UART_INTERVALO:
            _enviar_o_imprimir(uart, conteos)
            t_ult_uart = t_now

        # Visualizacion - partir del debug_frame del tracker
        vis = tracker.debug_frame(frame, objetos)

        # Capas adicionales
        epsilon_p = cfg.get("modelo", {}).get("epsilon_personas",  0)
        epsilon_v = cfg.get("modelo", {}).get("epsilon_vehiculos", 0)
        dibujar_roi(vis, roi)
        dibujar_linea(vis, linea_personas,  COLOR_LINEA_PERSONAS,  COLOR_EPSILON_PERSONAS,  epsilon_p)
        dibujar_linea(vis, linea_vehiculos, COLOR_LINEA_VEHICULOS, COLOR_EPSILON_VEHICULOS, epsilon_v)
        dibujar_panel(vis, conteos)

        # FPS total - esquina superior izquierda
        t_now  = time.time()
        fps    = 1.0 / (t_now - t_prev) if (t_now - t_prev) > 0 else 0.0
        t_prev = t_now
        cv2.putText(vis, f"FPS {fps:.1f}",
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)

        cv2.imshow("Aforo debug", vis)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:    # ESC
            break
        if key == 32:    # SPACE pausa
            cv2.waitKey(0)

    # Limpieza
    stop_event.set()  # indica al hilo receptor que pare
    cap.release()
    if uart is not None:
        uart.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
