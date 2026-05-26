# main.py
# Orquestador del Modo 2 (Aforo Engine).
# Hilo 1: captura frames de la camara y sobreescribe el frame actual.
# Hilo principal: lee el frame mas reciente, corre Tracker -> Counter -> UART.
# No tiene logica de negocio - solo une los modulos.
 
import threading
import time
import signal
import sys
import serial
import cv2
 
from config_manager import ConfigManager
from tracker        import Tracker
from counter        import Counter
 
# ---------------------------------------------------------------------------
# Configuracion UART - ajustar aqui
# ---------------------------------------------------------------------------
UART_PORT        = "/dev/ttyS0"   # puerto serial hacia el ESP32
UART_BAUD        = 115200
UART_SOLO_CAMBIOS = False          # True = mandar solo cuando hay cruces
 
 
# ---------------------------------------------------------------------------
# Hilo de captura
# ---------------------------------------------------------------------------
 
class CapturaVideo:
    """
    Hilo daemon que captura frames continuamente y sobreescribe el mas reciente.
    El hilo principal siempre lee el frame actual, no frames viejos acumulados.
    """
 
    def __init__(self, indice: int, ancho: int, alto: int):
        self.cap = cv2.VideoCapture(indice, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  ancho)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
 
        self.frame  = None
        self.ret    = False
        self.activo = True
        self._lock  = threading.Lock()
 
        self._thread = threading.Thread(target=self._capturar, daemon=True)
        self._thread.start()
 
    def _capturar(self):
        while self.activo:
            ret, frame = self.cap.read()
            if not ret:
                print("  [Captura] ret=False, camara desconectada.")
                self.activo = False
                break
            with self._lock:
                self.ret   = ret
                self.frame = frame
 
    def leer(self):
        with self._lock:
            if self.frame is None:
                return False, None
            return self.ret, self.frame.copy()
 
    def liberar(self):
        self.activo = False
        self._thread.join(timeout=2)
        self.cap.release()
 
  
# ---------------------------------------------------------------------------
# Motor principal
# ---------------------------------------------------------------------------
 
class AforoEngine:
    """
    Orquesta la captura, tracking, conteo y envio UART.
    """
 
    def __init__(self):
        print("[Engine] Iniciando...")
 
 
        self._cfg  = ConfigManager()
        self._uart = self._iniciar_uart()
        
        #carga de las instancias de clase - demora la carga del modelo yolo26n---------------
        # Avisar al ESP32 que el engine esta cargando
        self._enviar_estado("CARGANDO")
 
        self._tracker = Tracker(self._cfg)
        self._counter = Counter(self._cfg)
 
        # Avisar al ESP32 que el engine esta listo
        self._enviar_estado("LISTO")
        #------------------------------------------------------------------------------------
        self._activo  = True
 
        # Camara
        camara_cfg = self._cfg.get("camara", {})
        indice     = camara_cfg.get("indice", 0)
        ancho      = camara_cfg.get("ancho",  640)
        alto       = camara_cfg.get("alto",   480)
 
        print(f"[Engine] Abriendo camara {indice} ({ancho}x{alto})...")
        self._captura = CapturaVideo(indice, ancho, alto)
 
        # Esperar primer frame
        print("[Engine] Esperando primer frame...")
        while self._captura.frame is None:
            time.sleep(0.01)
        print("[Engine] Camara lista.")
 
        # Manejo de senal para apagado limpio
        signal.signal(signal.SIGTERM, self._apagar)
        signal.signal(signal.SIGINT,  self._apagar)
 
    def _iniciar_uart(self):
        """Abre el puerto serial. Devuelve None si falla."""
        try:
            uart = serial.Serial(UART_PORT, UART_BAUD, timeout=1)
            print(f"  [Engine] UART listo en {UART_PORT} a {UART_BAUD} baud.")
            return uart
        except Exception as e:
            print(f"  [Engine] Advertencia: no se pudo abrir UART ({e}). Corriendo sin serial.")
            return None
 
    def run(self):
        """Bucle principal: lee frame -> Tracker -> Counter -> UART."""
        print("[Engine] Modo 2 activo. Ctrl+C para detener.")
 
        while self._activo:
            ret, frame = self._captura.leer()
            if not ret or frame is None:
                if not self._captura.activo:
                    print("[Engine] Camara desconectada, cerrando.")
                    break
                continue
 
            # Pipeline
            objetos = self._tracker.trackear(frame)
            self._counter.actualizar(objetos)
            conteos = self._counter.get_conteos()
 
            # UART
            self._enviar_uart(conteos)
 
        self._cerrar()
 
     def _enviar_estado(self, estado: str):
        """
        Manda un mensaje de estado al ESP32.
        Formato: $ESTADO\n
        Diferente al paquete de datos que usa #.
 
        Estados usados:
            $CARGANDO  -> el engine esta iniciando
            $LISTO     -> el pipeline esta activo y contando
        """
        if self._uart is None:
            return
        try:
            self._uart.write(f"${estado}\n".encode("ascii"))
        except Exception as e:
            print(f"  [Engine] Error UART estado: {e}")

     def _enviar_uart(self, conteos: dict):
        """
        Serializa los conteos a CSV y los manda por UART.
 
        Formato: #p_in,p_out,p_aforo,p_din,p_dout,p_daforo,
                   v_in,v_out,v_aforo,v_din,v_dout,v_daforo\n
        usa #.
        Si UART_SOLO_CAMBIOS=True, solo manda cuando algun delta != 0.
        """
        if self._uart is None:
            return
 
        if UART_SOLO_CAMBIOS:
            hay_cambio = any([
                conteos["personas_delta_in"],
                conteos["personas_delta_out"],
                conteos["vehiculos_delta_in"],
                conteos["vehiculos_delta_out"],
            ])
            if not hay_cambio:
                return
 
        mensaje = (
            f"#{conteos['personas_in']},"
            f"{conteos['personas_out']},"
            f"{conteos['personas_aforo']},"
            f"{conteos['personas_delta_in']},"
            f"{conteos['personas_delta_out']},"
            f"{conteos['personas_delta_aforo']},"
            f"{conteos['vehiculos_in']},"
            f"{conteos['vehiculos_out']},"
            f"{conteos['vehiculos_aforo']},"
            f"{conteos['vehiculos_delta_in']},"
            f"{conteos['vehiculos_delta_out']},"
            f"{conteos['vehiculos_delta_aforo']}\n"
        )
 
        try:
            self._uart.write(mensaje.encode("ascii"))
        except Exception as e:
            print(f"  [Engine] Error UART: {e}")
 
    def _apagar(self, signum=None, frame=None):
        """Manejador de SIGTERM y SIGINT para apagado limpio."""
        print("\n[Engine] Senal de apagado recibida, cerrando...")
        self._activo = False
 
    def _cerrar(self):
        """Libera todos los recursos."""
        self._captura.liberar()
        if self._uart:
            self._uart.close()
        print("[Engine] Cerrado.")
 
 
# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    engine = AforoEngine()
    engine.run()
 
