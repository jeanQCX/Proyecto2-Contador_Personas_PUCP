# main_debug.py
# Gemelo de main.py orientado a desarrollo y validacion.
# Muestra ventana OpenCV con toda la informacion del pipeline:
# ROI, lineas de conteo, p3, bbox, centroides, trayectorias, FPS y conteos.
# NO usar en produccion — solo desarrollo.

#warning wayland----------------------------------------
import os
os.environ["QT_QPA_PLATFORM"] = "xcb"
#-------------------------------------------------------

import time
import math
import cv2

from config_manager import ConfigManager
from tracker        import Tracker
from counter        import Counter
from geometry       import linea_desde_config, roi_desde_config

# ---------------------------------------------------------------------------
# Fuente de video — cambiar aqui
# ---------------------------------------------------------------------------
FUENTE = "../Teros_v1c4.mp4"   # path a video
# FUENTE = None                 # None = camara

# ---------------------------------------------------------------------------
# Colores BGR para visualizacion
# ---------------------------------------------------------------------------
COLOR_ROI            = (0,   255, 255)   # amarillo
COLOR_LINEA_PERSONAS = (0,   255, 0  )   # verde
COLOR_LINEA_VEHICULOS= (255, 0,   0  )   # azul
COLOR_P3             = (0,   0,   255)   # rojo — zona positiva
COLOR_TEXTO          = (255, 255, 255)   # blanco
COLOR_PANEL_BG       = (30,  30,  30 )   # gris oscuro panel
COLOR_EPSILON_PERSONAS  = (50, 255, 50)      # verde lima
COLOR_EPSILON_VEHICULOS = (255, 200, 100)    # azul claro


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


def dibujar_linea(vis, linea, color, color_epsilon, nombre, epsilon_px=0):
    """Dibuja la linea de conteo, bandas epsilon punteadas, extremos y p3."""
    if linea is None:
        return
    p1, p2, p3 = linea
    pt1 = (int(p1[0]), int(p1[1]))
    pt2 = (int(p2[0]), int(p2[1]))
    pt3 = (int(p3[0]), int(p3[1]))

    # Bandas epsilon — lineas paralelas punteadas
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

    # P3 — zona positiva, mismo color que la linea, mas pequeño
    cv2.circle(vis, pt3, 4, color, -1)
    cv2.putText(vis, "p3", (pt3[0] + 6, pt3[1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # Nombre en p2
    cv2.putText(vis, nombre, (pt2[0] + 6, pt2[1] + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


def dibujar_panel(vis, conteos):
    """
    Dibuja un panel semitransparente en la esquina superior derecha
    con los conteos de personas y vehiculos.
    """
    h, w = vis.shape[:2]

    lineas = [
        "PERSONAS",
        f"  in:    {conteos['personas_in']}",
        f"  out:   {conteos['personas_out']}",
        f"  aforo: {conteos['personas_aforo']}",
        "",
        "VEHICULOS",
        f"  in:    {conteos['vehiculos_in']}",
        f"  out:   {conteos['vehiculos_out']}",
        f"  aforo: {conteos['vehiculos_aforo']}",
    ]

    margen   = 5        #espacio entre el borde del panel y el texto
    linea_h  = 15     #altura de la separacion entre textos
    ancho_panel = 110    #ancho del panel
    alto_panel  = len(lineas) * linea_h + margen * 2

    x1 = w - ancho_panel - margen
    y1 = margen
    x2 = w - margen
    y2 = y1 + alto_panel

    # Fondo semitransparente
    overlay = vis.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), COLOR_PANEL_BG, -1)
    cv2.addWeighted(overlay, 0.4, vis, 0.6, 0, vis)

    # Texto
    for i, texto in enumerate(lineas):
        if not texto:
            continue
        color = COLOR_TEXTO
        if texto in ("PERSONAS", "VEHICULOS"):
            color = COLOR_LINEA_PERSONAS if texto == "PERSONAS" else COLOR_LINEA_VEHICULOS
        cy = y1 + margen + i * linea_h + 14
        cv2.putText(vis, texto, (x1 + 8, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def main():
    cfg     = ConfigManager()
    tracker = Tracker(cfg)
    counter = Counter(cfg)
 
    # Leer lineas y ROI del config para dibujarlas
    linea_personas  = linea_desde_config(cfg.get("linea_personas",  {}))
    linea_vehiculos = linea_desde_config(cfg.get("linea_vehiculos", {}))
    roi             = roi_desde_config(cfg.get("roi", {}))
 
    cap     = abrir_fuente(cfg)
    t_prev  = time.time()
    fps     = 0.0
 
    print("  [Debug] ESC para salir, SPACE pausa.")
 
    while True:
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
 
        # Visualizacion -partir del debug_frame del tracker
        vis = tracker.debug_frame(frame, objetos)
 
        # Capas adicionales
        epsilon_p = cfg.get("modelo", {}).get("epsilon_personas",  0)
        epsilon_v = cfg.get("modelo", {}).get("epsilon_vehiculos", 0)
        dibujar_roi(vis, roi)
        dibujar_linea(vis, linea_personas,  COLOR_LINEA_PERSONAS,  COLOR_EPSILON_PERSONAS,  "personas",  epsilon_p)
        dibujar_linea(vis, linea_vehiculos, COLOR_LINEA_VEHICULOS, COLOR_EPSILON_VEHICULOS, "vehiculos", epsilon_v)
        dibujar_panel(vis, conteos)
 
        # FPS total
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
 
    cap.release()
    cv2.destroyAllWindows()
 

if __name__ == "__main__":
    main()
