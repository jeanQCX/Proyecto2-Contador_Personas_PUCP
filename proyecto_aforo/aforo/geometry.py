# geometry.py
# Matematica pura para el sistema de aforo.
# Usada por tracker.py (centroide, roi_desde_config) y
# counter.py (detectar_cruce, linea_desde_config).
# No depende de ningun otro modulo del proyecto.
 

# ---------------------------------------------------------------------------
# Centroide
# ---------------------------------------------------------------------------
 
def centroide(bbox: tuple) -> tuple:
    """
    Calcula el centroide de un bounding box.
    bbox: (x1, y1, x2, y2)
    Devuelve (cx, cy).
    """
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
 
 
# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
 
def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    """Producto cruzado 2D. Devuelve escalar (componente Z)."""
    return ax * by - ay * bx
 
 
def _signo_lado(p1: tuple, p2: tuple, t: tuple) -> float:
    """
    Producto cruzado de (P2-P1) x (T-P1).
    El signo indica de que lado de la linea P1->P2 esta el punto T.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    tx = t[0]  - p1[0]
    ty = t[1]  - p1[1]
    return _cross(dx, dy, tx, ty)
 
def _longitud(p1: tuple, p2: tuple) -> float:
    """Longitud euclidiana del segmento p1->p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return (dx*dx + dy*dy) ** 0.5
 
# ---------------------------------------------------------------------------
# Logica de cruce unica funcion publica que usa counter.py
# ---------------------------------------------------------------------------
 
def detectar_cruce(pos_anterior: tuple, pos_actual: tuple,
                   p1: tuple, p2: tuple, p3: tuple, epsilon_px: float = 5.0) -> int:
    """
    Determina si un objeto cruzo la linea entre dos posiciones consecutivas
    y en que direccion lo hizo.
 
    La linea es INFINITA definida por la direccion p1->p2.
    p3 es el punto de referencia que define cual lado es el positivo.
 
    Banda de histeresis: si el centroide esta a menos de epsilon_px pixeles
    de la linea, se considera zona neutra y no se cuenta. Esto elimina
    falsos cruces por jitter cuando el objeto esta cerca de la linea.
    epsilon_px se lee del config.json y se pasa desde counter.py.
 
    Metodo: comparacion de signos normalizados por longitud de linea.
 
    Devuelve:
        +1  -> cruzo hacia la zona positiva  (entrada)
        -1  -> cruzo hacia la zona negativa  (salida)
         0  -> no cruzo o esta en zona neutra
    """
    long_linea = _longitud(p1, p2)
    if long_linea < 1e-10:
        return 0  # linea degenerada, p1 y p2 son el mismo punto
 
    signo_anterior = _signo_lado(p1, p2, pos_anterior)
    signo_actual   = _signo_lado(p1, p2, pos_actual)
 
    # Banda de histeresis distancia perpendicular a la linea en pixeles
    dist_anterior = abs(signo_anterior) / long_linea
    dist_actual   = abs(signo_actual)   / long_linea
 
    if dist_anterior < epsilon_px or dist_actual < epsilon_px:
        return 0  # uno de los dos puntos esta en la zona neutra
 
    # Si el signo no cambio, no cruzo
    if (signo_anterior * signo_actual) > 0:
        return 0
 
    # Cruzo determinar direccion con p3
    signo_ref        = _signo_lado(p1, p2, p3)
    en_zona_positiva = (signo_ref * signo_actual) > 0  #mismo signo, da +, diferente da -
    return +1 if en_zona_positiva else -1
 
    
def detectar_cruce_segmento(pos_anterior: tuple, pos_actual: tuple,
                             p1: tuple, p2: tuple, p3: tuple, epsilon_px: float = 5.0) -> int:
    """
    Igual que detectar_cruce pero la linea es un SEGMENTO finito p1->p2.
    Solo cuenta si la trayectoria cruza dentro del segmento.
    Usa parametrizacion: t (trayectoria) y u (segmento) ambos entre 0 y 1.
 
    Devuelve:
        +1  -> cruzo hacia la zona positiva
        -1  -> cruzo hacia la zona negativa
         0  -> no cruzo
    """
    
    # Verificar si la trayectoria cruza el segmento p1->p2
    # Usando parametrizacion: trayectoria = pos_anterior + t*r, linea = p1 + u*s
    # pos_anterior + t*r = p1 + u*s   => p1 - pos_ant = t*r - u*s
    # qp x s = t * r x s - u * s x s , qp x r = t*r x r - u* s x r
    # t = qp x s / r x s  ,  u = qp x r / r x s
    
    long_linea = _longitud(p1, p2)
    if long_linea < 1e-10:
        return 0
 
    # Banda de histeresis
    signo_anterior = _signo_lado(p1, p2, pos_anterior)
    signo_actual   = _signo_lado(p1, p2, pos_actual)
 
    dist_anterior = abs(signo_anterior) / long_linea
    dist_actual   = abs(signo_actual)   / long_linea
 
    if dist_anterior < epsilon_px or dist_actual < epsilon_px:
        return 0
 
    # Parametrizacion para segmento estricto
    rx = pos_actual[0] - pos_anterior[0]
    ry = pos_actual[1] - pos_anterior[1]
    sx = p2[0] - p1[0]
    sy = p2[1] - p1[1]
 
    rxs = _cross(rx, ry, sx, sy)
    if abs(rxs) < 1e-10:
        return 0  # paralelos
 
    qpx = p1[0] - pos_anterior[0]
    qpy = p1[1] - pos_anterior[1]
 
    t = _cross(qpx, qpy, sx, sy) / rxs
    u = _cross(qpx, qpy, rx, ry) / rxs
 
    if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
        return 0
 
    signo_ref        = _signo_lado(p1, p2, p3)
    signo_test       = _signo_lado(p1, p2, pos_actual)
    if signo_test == 0:
        return 0
    en_zona_positiva = (signo_ref * signo_test) > 0
    return +1 if en_zona_positiva else -1
    
# ---------------------------------------------------------------------------
# Helpers de config.json -> tuplas
# ---------------------------------------------------------------------------
 
def _punto_desde_config(p):
    """Convierte un punto del config (lista o dict) a tupla (x, y)."""
    if p is None:
        return None
    if isinstance(p, (list, tuple)):
        return (float(p[0]), float(p[1]))
    if isinstance(p, dict):
        return (float(p["x"]), float(p["y"]))
    return None
 
 
def linea_desde_config(config_linea: dict):
    """
    Convierte una entrada de linea del config.json a (p1, p2, p3).
    Devuelve None si alguno de los puntos es null (linea no configurada).
    """
    p1 = _punto_desde_config(config_linea.get("p1"))
    p2 = _punto_desde_config(config_linea.get("p2"))
    p3 = _punto_desde_config(config_linea.get("p3"))
 
    if p1 is None or p2 is None or p3 is None:
        return None
 
    return (p1, p2, p3)
 
 
def roi_desde_config(config_roi: dict):
    """
    Convierte la entrada de ROI del config.json a (p1, p2).
    Devuelve None si alguno de los puntos es null (ROI no configurado).
    """
    p1 = _punto_desde_config(config_roi.get("p1"))
    p2 = _punto_desde_config(config_roi.get("p2"))
 
    if p1 is None or p2 is None:
        return None
 
    return (p1, p2)
