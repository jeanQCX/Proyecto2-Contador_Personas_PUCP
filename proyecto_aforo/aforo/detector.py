# detector.py
# Clase Detector: carga YOLOv8n NCNN una vez, recibe frame y devuelve
# bounding boxes con clase y confianza en coordenadas del frame completo.
# El recorte de ROI se aplica antes de la inferencia para reducir carga.
# No depende de geometry.py ni de ningun otro modulo del proyecto.
 
import time
import cv2
from ultralytics import YOLO
from config_manager import ConfigManager
 
# ---------------------------------------------------------------------------
# Configuracion del modelo ajustar aqui, no en config.json
# ---------------------------------------------------------------------------
MODELO_PATH = "yolo26n_rx256_ncnn_model"   # carpeta del modelo NCNN fine-tuned
 
# Clases COCO (modelo actual):
#   0=persona, 2=auto, 3=moto, 5=bus, 7=camion
# Para el fine-tuned (2 clases propias):
#   cambiar a CLASES_VALIDAS = [0, 1]
#   y TIPO_POR_CLASE = {0: "persona", 1: "vehiculo"}
CLASES_VALIDAS = [0, 2, 3, 5, 7]
 
TIPO_POR_CLASE = {
    0: "persona",
    2: "vehiculo",
    3: "vehiculo",
    5: "vehiculo",
    7: "vehiculo",
}
 
# Colores BGR para debug
COLOR_PERSONA  = (0, 255, 0)    # verde
COLOR_VEHICULO = (255, 0, 0)    # naranja
COLOR_ROI      = (0, 255, 255)  # amarillo
 
 
class Detector:
    """
    Envuelve el modelo YOLOv8n NCNN.
 
    Uso tipico:
        cfg      = ConfigManager()
        detector = Detector(cfg)
        boxes    = detector.detectar(frame)
 
    Cada elemento de boxes es un dict:
        {
            "bbox":       (x1, y1, x2, y2),  # coordenadas en el frame completo
            "confianza":  float,
            "clase":      int,                # ID COCO original
            "tipo":       str,                # "persona" o "vehiculo"
        }
    """
 
    def __init__(self, cfg: ConfigManager):
        conf = cfg.get("modelo", {}).get("confianza", 0.5)
        iou  = cfg.get("modelo", {}).get("iou", 0.4)
 
        self._conf = conf
        self._iou  = iou
        self._roi  = self._leer_roi(cfg)
 
        # Estado interno para FPS de debug
        self._t_anterior = 0.0
        self._fps_modelo  = 0.0
 
        print(f"  [Detector] Cargando modelo: {MODELO_PATH}")
        self._model = YOLO(MODELO_PATH, task="detect")
        print(f"  [Detector] Modelo listo. conf={conf} iou={iou}")
        if self._roi:
            print(f"  [Detector] ROI activo: {self._roi}")
        else:
            print("  [Detector] Advertencia: ROI no configurado, se usa frame completo.")
 
    # ------------------------------------------------------------------
    # Interfaz publica
    # ------------------------------------------------------------------
 
    def detectar(self, frame):
        """
        Corre inferencia sobre el frame y devuelve lista de detecciones.
 
        Si hay ROI configurado, recorta el frame antes de inferencia
        y traduce las coordenadas al frame completo antes de devolver.
 
        Parametros:
            frame : numpy array BGR (frame completo de la camara)
 
        Devuelve:
            list[dict] con claves bbox, confianza, clase, tipo.
            Lista vacia si no hay detecciones.
        """
        if self._roi:
            frame_inferencia, offset_x, offset_y = self._recortar_roi(frame)
        else:
            frame_inferencia, offset_x, offset_y = frame, 0, 0
 
        t1 = time.time()
        results = self._model(
            frame_inferencia,
            device="cpu",
            conf=self._conf,
            iou=self._iou,
            classes=CLASES_VALIDAS,
            verbose=False,
        )
        t2 = time.time()
 
        dt = t2 - t1
        self._fps_modelo = 1.0 / dt if dt > 0 else 0.0
 
        return self._parsear(results, offset_x, offset_y)

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------
 
    def debug_frame(self, frame, detecciones):
        """
        Dibuja bounding boxes, etiquetas, ROI y FPS sobre el frame.
        Devuelve una copia del frame con las anotaciones.
        Solo para desarrollo no llamar en produccion.
 
        Parametros:
            frame       : frame BGR original (sin modificar)
            detecciones : lista devuelta por detectar()
        """
        vis = frame.copy()
 
        # ROI
        if self._roi:
            x_min, y_min, x_max, y_max = self._roi
            cv2.rectangle(vis, (x_min, y_min), (x_max, y_max), COLOR_ROI, 2)
            cv2.putText(vis, "ROI", (x_min + 4, y_min + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_ROI, 2)
 
        # Bounding boxes
        for det in detecciones:
            x1, y1, x2, y2 = (int(v) for v in det["bbox"])
            color  = COLOR_PERSONA if det["tipo"] == "persona" else COLOR_VEHICULO
            etiq   = f"{det['tipo']} {det['confianza']:.2f}"
 
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            cv2.putText(vis, etiq, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
 
        # FPS del modelo
        cv2.putText(vis, f"YOLO {self._fps_modelo:.1f} fps",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
 
        return vis
 
    def run_debug(self, cfg: ConfigManager, fuente=None):
        """
        Bucle de debug autonomo: muestra ventana OpenCV con detecciones,
        ROI y FPS hasta que se presione ESC.
        Solo para desarrollo.
 
        Parametros:
            cfg    : ConfigManager con la configuracion del proyecto.
            fuente : None        ? usa la camara definida en config.json
                     str (path)  ? abre el archivo de video indicado
                                   ej: fuente="video.mp4"
 
        Ejemplos:
            det.run_debug(cfg)                       # camara
            det.run_debug(cfg, fuente="video.mp4")   # video
        """
        if fuente is not None:
            # ---- VIDEO ----
            cap = cv2.VideoCapture(fuente)
            if not cap.isOpened():
                print(f"  [Detector] No se pudo abrir el video: {fuente}")
                return
            modo = f"video: {fuente}"
        else:
            # ---- CAMARA ----
            camara_cfg = cfg.get("camara", {})
            indice     = camara_cfg.get("indice", 0)
            ancho      = camara_cfg.get("ancho", 640)
            alto       = camara_cfg.get("alto",  480)
 
            cap = cv2.VideoCapture(indice, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  ancho)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
            modo = f"camara indice {indice}"
 
        print(f"  [Detector] Debug activo ({modo}), presiona ESC para salir.")
 
        fps_total = 0.0
        t_prev    = time.time()
 
        while True:
            ret, frame = cap.read()
            frame = cv2.resize(frame, (640, 480)) #<--------------- OJO, usar cuando se pone  VIDEO
            if not ret:
                # En video es fin de archivo, en camara es error
                if fuente is not None:
                    print("  [Detector] Fin del video.")
                else:
                    print("  [Detector] Error leyendo camara.")
                break
 
            detecciones = self.detectar(frame)
            vis         = self.debug_frame(frame, detecciones)
 
            # FPS total (captura + inferencia)
            t_now     = time.time()
            fps_total = 1.0 / (t_now - t_prev) if (t_now - t_prev) > 0 else 0.0
            t_prev    = t_now
 
            cv2.putText(vis, f"FPS {fps_total:.1f}",
                        (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2)
 
            cv2.imshow("Detector debug", vis)
 
            # ESC sale, SPACE pausa (util en video)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:    # ESC
                break
            if key == 32:    # SPACE pausa hasta otra tecla
                cv2.waitKey(0)
 
        cap.release()
        cv2.destroyAllWindows()
        
    # ------------------------------------------------------------------
    # Privados
    # ------------------------------------------------------------------
 
    def _leer_roi(self, cfg: ConfigManager):
        """
        Lee el ROI del config.json y lo devuelve como
        (x_min, y_min, x_max, y_max) en pixeles enteros, o None.
        """
        roi = cfg.get("roi", {})
        p1  = roi.get("p1")
        p2  = roi.get("p2")
 
        if p1 is None or p2 is None:
            return None
 
        # Soporta lista [x, y] o dict {"x":..., "y":...}
        x1, y1 = self._extraer_xy(p1)
        x2, y2 = self._extraer_xy(p2)
 
        return (
            int(min(x1, x2)),
            int(min(y1, y2)),
            int(max(x1, x2)),
            int(max(y1, y2)),
        )
 
    def _extraer_xy(self, punto):
        """Convierte punto de config (lista o dict) a (x, y)."""
        if isinstance(punto, (list, tuple)):
            return float(punto[0]), float(punto[1])
        if isinstance(punto, dict):
            return float(punto["x"]), float(punto["y"])
        raise ValueError(f"Formato de punto no reconocido: {punto}")
 
    def _recortar_roi(self, frame):
        """
        Recorta el frame al rectangulo del ROI.
 
        Devuelve:
            (frame_recortado, offset_x, offset_y)
 
        Los offsets se suman luego a las coords de bbox
        para traducirlas al frame completo.
        """
        x_min, y_min, x_max, y_max = self._roi
        h, w = frame.shape[:2]
 
        # Clamp por seguridad
        x_min = max(0, x_min)
        y_min = max(0, y_min)
        x_max = min(w, x_max)
        y_max = min(h, y_max)
 
        recorte = frame[y_min:y_max, x_min:x_max]
        return recorte, x_min, y_min
 
    def _parsear(self, results, offset_x: int, offset_y: int):
        """
        Convierte la salida de ultralytics a lista de dicts limpios.
        Suma los offsets para que las coords sean del frame completo.
        """
        detecciones = []
 
        for result in results:
            if result.boxes is None:
                continue
 
            for box in result.boxes:
                clase = int(box.cls[0])
                tipo  = TIPO_POR_CLASE.get(clase)
                if tipo is None:
                    continue
 
                x1, y1, x2, y2 = box.xyxy[0].tolist()
 
                detecciones.append({
                    "bbox":      (
                        x1 + offset_x,
                        y1 + offset_y,
                        x2 + offset_x,
                        y2 + offset_y,
                    ),
                    "confianza": float(box.conf[0]),
                    "clase":     clase,
                    "tipo":      tipo,
                })
 
        return detecciones
 
 
if __name__ == "__main__":
    cfg = ConfigManager()
    det = Detector(cfg)
    # CAMARA
    #det.run_debug(cfg )
    
    # VIDEO, Un nivel arriba
    det.run_debug(cfg, fuente="../Teros_v1c4.mp4")
