# tracker.py
# Clase Tracker: corre model.track() con ByteTrack, mantiene historial de
# posiciones por ID y devuelve los datos que necesita counter.py.
# No depende de geometry.py
 
import time
import cv2
from ultralytics import YOLO
from config_manager import ConfigManager
 
# ---------------------------------------------------------------------------
# Configuracion del modelo
# ---------------------------------------------------------------------------
MODELO_PATH = "yolo26n_rx256_ncnn_model"   # carpeta del modelo NCNN fine-tuned
TRACKER_CONFIG = "bytetrack.yaml"
#TRACKER_CONFIG = "bytetrack_mine.yaml"   #yaml personalizado
 
CLASES_VALIDAS = [0, 2, 3, 5, 7]
 
TIPO_POR_CLASE = {
    0: "persona",
    2: "vehiculo",
    3: "vehiculo",
    5: "vehiculo",
    7: "vehiculo",
}
 
# Colores BGR para debug
COLOR_PERSONA   = (0, 255, 0)        #Verde
COLOR_VEHICULO  = (255, 0, 0)        #Azul
COLOR_CENTROIDE = (0, 0, 255)        #Rojo
COLOR_ROI       = (0, 255, 255)      #Amarillo
COLOR_ID        = (255, 255, 255)    #Blanco
 
 
class Tracker:
    """
    Wrapper de model.track() con ByteTrack.
    Mantiene historial de posiciones por ID para que counter.py
    pueda detectar cruces de linea.
 
    Uso tipico:
        cfg     = ConfigManager()
        tracker = Tracker(cfg)
        objetos = tracker.trackear(frame)
 
    Cada elemento de "objetos" es un dict:
        {
            "track_id":    int,
            "tipo":        str,           # "persona" o "vehiculo"
            "pos_actual":  (cx, cy),
            "pos_anterior": (cx, cy) | None,
            "bbox":        (x1, y1, x2, y2),
        }
    """
 
    def __init__(self, cfg: ConfigManager):
        conf = cfg.get("modelo", {}).get("confianza", 0.5)
        iou  = cfg.get("modelo", {}).get("iou", 0.4)
 
        self._conf = conf
        self._iou  = iou
        self._roi  = self._leer_roi(cfg)
 
        # Historial: {track_id: (cx, cy)} ultima posicion conocida
        self._historial = {}
 
        # FPS interno para debug
        self._fps = 0.0
 
        print(f"  [Tracker] Cargando modelo: {MODELO_PATH}")
        self._model = YOLO(MODELO_PATH, task="detect")
        print(f"  [Tracker] Modelo listo. tracker={TRACKER_CONFIG} conf={conf} iou={iou}")
        if self._roi:
            print(f"  [Tracker] ROI activo: {self._roi}")
        else:
            print("  [Tracker] Advertencia: ROI no configurado, se usa frame completo.")
 
    # ------------------------------------------------------------------
    # Interfaz publica
    # ------------------------------------------------------------------
 
    def trackear(self, frame):
        """
        Corre tracking sobre el frame y devuelve lista de objetos trackeados.
 
        Si hay ROI configurado, recorta el frame antes de la inferencia
        y traduce las coordenadas al frame completo.
 
        Parametros:
            frame : numpy array BGR (frame completo de la camara)
 
        Devuelve:
            list[dict] con claves track_id, tipo, pos_actual, pos_anterior, bbox.
            Lista vacia si no hay detecciones o ningun objeto tiene ID asignado.
        """
        if self._roi:
            frame_inferencia, offset_x, offset_y = self._recortar_roi(frame)
        else:
            frame_inferencia, offset_x, offset_y = frame, 0, 0
 
        t1 = time.time()
        results = self._model.track(
            frame_inferencia,
            tracker=TRACKER_CONFIG,
            persist=True,
            classes=CLASES_VALIDAS,
            conf=self._conf,
            iou=self._iou,
            device="cpu",
            verbose=False,
        )
        t2 = time.time()
 
        dt = t2 - t1
        self._fps = 1.0 / dt if dt > 0 else 0.0
 
        return self._parsear(results, offset_x, offset_y)
 
    def reset(self):
        """Limpia el historial de IDs. Util si se reinicia el conteo."""
        self._historial.clear()
        print("  [Tracker] Historial de IDs limpiado.")
        
        
    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------
 
    def debug_frame(self, frame, objetos):
        """
        Dibuja boxes, centroides, IDs, tipo y ROI sobre el frame.
        Devuelve una copia anotada sin modificar el original.
        Solo para desarrollo.
        """
        vis = frame.copy()
 
        # ROI
        if self._roi:
            x_min, y_min, x_max, y_max = self._roi
            cv2.rectangle(vis, (x_min, y_min), (x_max, y_max), COLOR_ROI, 2)
            cv2.putText(vis, "ROI", (x_min + 4, y_min + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_ROI, 2)
 
        for obj in objetos:
            x1, y1, x2, y2 = (int(v) for v in obj["bbox"])
            cx, cy          = int(obj["pos_actual"][0]), int(obj["pos_actual"][1])
            color           = COLOR_PERSONA if obj["tipo"] == "persona" else COLOR_VEHICULO
            #etiq            = f"ID{obj['track_id']} {obj['tipo']}"   #con tipo, personas o vehiculos
            etiq            = f"ID{obj['track_id']}"   #solo IDs
 
            # Bounding box
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
 
            # Etiqueta
            cv2.putText(vis, etiq, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
 
            # Centroide
            cv2.circle(vis, (cx, cy), 5, COLOR_CENTROIDE, -1)
 
            # Linea anterior ? actual si hay historial
            if obj["pos_anterior"] is not None:
                px, py = int(obj["pos_anterior"][0]), int(obj["pos_anterior"][1])
                cv2.line(vis, (px, py), (cx, cy), color, 2)
 
        # FPS
        cv2.putText(vis, f"Tracker {self._fps:.1f}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
 
        return vis
 
    def run_debug(self, cfg: ConfigManager, fuente=None):
        """
        Bucle de debug autonomo. ESC para salir, SPACE pausa (util en video).
 
        Parametros:
            cfg    : ConfigManager
            fuente : None       ? camara definida en config.json
                     str (path) ? archivo de video, ej: "../video.mp4"
        """
        if fuente is not None:
            cap  = cv2.VideoCapture(fuente)
            if not cap.isOpened():
                print(f"  [Tracker] No se pudo abrir el video: {fuente}")
                return
            modo = f"video: {fuente}"
        else:
            camara_cfg = cfg.get("camara", {})
            indice     = camara_cfg.get("indice", 0)
            ancho      = camara_cfg.get("ancho", 640)
            alto       = camara_cfg.get("alto",  480)
 
            cap = cv2.VideoCapture(indice, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  ancho)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
            modo = f"camara indice {indice}"
 
        print(f"  [Tracker] Debug activo ({modo})  presiona ESC para salir.")
 
        fps_total = 0.0
        t_prev    = time.time()
 
        while True:
            ret, frame = cap.read()
            if not ret:
                print("  [Tracker] Fin del video." if fuente else "  [Tracker] Error leyendo camara.")
                break
                
            frame = cv2.resize(frame, (640, 480)) #<--------------- OJO, usar cuando se pone  VIDEO
            
            objetos = self.trackear(frame)
            vis     = self.debug_frame(frame, objetos)
 
            t_now     = time.time()
            fps_total = 1.0 / (t_now - t_prev) if (t_now - t_prev) > 0 else 0.0
            t_prev    = t_now
 
            cv2.putText(vis, f"FPS {fps_total:.1f}",
                        (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
 
            cv2.imshow("Tracker debug", vis)
 
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if key == 32:
                cv2.waitKey(0)
 
        cap.release()
        cv2.destroyAllWindows()
        
        
    # ------------------------------------------------------------------
    # Privados
    # ------------------------------------------------------------------
 
    def _parsear(self, results, offset_x, offset_y):
        """
        Extrae IDs, centroides y tipo de la salida de model.track().
        Actualiza el historial y arma los dicts para counter.py.
        """
        objetos = []
 
        if not results or results[0].boxes is None:
            return objetos
 
        boxes = results[0].boxes
 
        for box in boxes:
            if box.id is None:
                continue
 
            track_id        = int(box.id[0])
            clase           = int(box.cls[0])
            tipo            = TIPO_POR_CLASE.get(clase)
            if tipo is None:
                continue
 
            x1, y1, x2, y2 = box.xyxy[0].tolist()
 
            # Traducir coordenadas al frame completo
            x1 += offset_x; y1 += offset_y
            x2 += offset_x; y2 += offset_y
 
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
 
            pos_anterior            = self._historial.get(track_id)
            pos_actual              = (cx, cy)
            self._historial[track_id] = pos_actual
 
            objetos.append({
                "track_id":    track_id,
                "tipo":        tipo,
                "pos_actual":  pos_actual,
                "pos_anterior": pos_anterior,
                "bbox":        (x1, y1, x2, y2),
            })
 
        return objetos
 
    def _leer_roi(self, cfg: ConfigManager):
        roi = cfg.get("roi", {})
        p1  = roi.get("p1")
        p2  = roi.get("p2")
        if p1 is None or p2 is None:
            return None
        x1, y1 = self._extraer_xy(p1)
        x2, y2 = self._extraer_xy(p2)
        return (int(min(x1,x2)), int(min(y1,y2)), int(max(x1,x2)), int(max(y1,y2)))
 
    def _extraer_xy(self, punto):
        if isinstance(punto, (list, tuple)):
            return float(punto[0]), float(punto[1])
        if isinstance(punto, dict):
            return float(punto["x"]), float(punto["y"])
        raise ValueError(f"Formato de punto no reconocido: {punto}")
 
    def _recortar_roi(self, frame):
        x_min, y_min, x_max, y_max = self._roi
        h, w = frame.shape[:2]
        x_min = max(0, x_min); y_min = max(0, y_min)
        x_max = min(w, x_max); y_max = min(h, y_max)
        recorte = frame[y_min:y_max, x_min:x_max]
        return recorte, x_min, y_min
        
if __name__ == "__main__":
    cfg     = ConfigManager()
    tracker = Tracker(cfg)
    # CAMARA
    #tracker.run_debug(cfg)

    # VIDEO, un nivel arriba
    tracker.run_debug(cfg, fuente="../Teros_v1c4.mp4")
