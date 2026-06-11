# main.py
# Orquestador del Modo 2 (Aforo Engine).
# Hilo 1: captura frames de la camara y sobreescribe el frame actual.
# Hilo principal: lee el frame mas reciente, corre Tracker -> Counter -> UART.
# No tiene logica de negocio - solo une los modulos.

import threading
import time
import signal
import sys
import subprocess
import serial
import cv2

from config_manager import ConfigManager
from tracker        import Tracker
from counter        import Counter


# ---------------------------------------------------------------------------
# Hilo receptor UART - escucha comandos del ESP32
# ---------------------------------------------------------------------------

class ReceptorUART:
    """
    Hilo daemon que escucha comandos entrantes del ESP32 por UART.

    Comandos soportados (prefijo !):
        !APAGAR  -- cierra el engine y apaga el sistema operativo

    El hilo bloquea en readline() esperando una linea completa terminada en \n.
    Al recibir un comando valido llama al metodo correspondiente del engine.

    Para agregar nuevos comandos en el futuro, agregar un elif
    en el metodo _procesar_comando().
    """

    def __init__(self, uart, engine):
        # uart   -- objeto serial.Serial ya abierto, compartido con el engine
        # engine -- referencia al AforoEngine para poder llamar sus metodos
        self._uart   = uart
        self._engine = engine
        self._activo = True

        self._thread = threading.Thread(target=self._escuchar, daemon=True)
        self._thread.start()
        print("  [Receptor] Hilo UART receptor activo.")

    def _escuchar(self):
        """Bucle bloqueante: espera lineas del ESP32 y las procesa."""
        while self._activo:
            try:
                # readline() bloquea hasta recibir \n o timeout del serial
                linea = self._uart.readline()
                if linea:
                    self._procesar_comando(linea.decode("ascii", errors="ignore").strip())
            except Exception as e:
                if self._activo:
                    print(f"  [Receptor] Error leyendo UART: {e}")

    def _procesar_comando(self, cmd: str):
        """
        Interpreta el comando recibido y ejecuta la accion correspondiente.
        Solo acepta comandos con prefijo !
        """
        if not cmd.startswith("!"):
            return  # ignorar lineas que no son comandos

        print(f"  [Receptor] Comando recibido: {cmd}")

        if cmd == "!APAGAR":
            self._engine.apagado_sistema()
        # --- futuros comandos aqui ---
        # elif cmd == "!RESET":
        #     self._engine.reset_conteos()
        else:
            print(f"  [Receptor] Comando desconocido: {cmd}")

    def detener(self):
        """Detiene el hilo receptor."""
        self._activo = False


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

    Configuracion UART leida de config.json bajo la clave "uart":
        puerto    -- puerto serie, ej: "/dev/ttyS0"
        baudrate  -- velocidad, ej: 115200
        intervalo -- segundos entre tramas, ej: 1.0
    """

    def __init__(self):
        print("[Engine] Iniciando...")

        self._cfg = ConfigManager()

        # Leer config UART
        uart_cfg          = self._cfg.get("uart", {})
        self._uart_puerto = uart_cfg.get("puerto",    "/dev/ttyS0")
        self._uart_baud   = uart_cfg.get("baudrate",  115200)
        self._intervalo   = float(uart_cfg.get("intervalo", 1.0))

        self._uart = self._iniciar_uart()

        # Arrancar hilo receptor si el UART esta disponible
        # El receptor escucha comandos del ESP32 (ej: !APAGAR)
        if self._uart is not None:
            self._receptor = ReceptorUART(self._uart, self)
        else:
            self._receptor = None

        # Avisar al ESP32 que el engine esta cargando
        # (el modelo YOLO tarda en cargar)
        self._enviar_estado("CARGANDO")

        self._tracker = Tracker(self._cfg)
        self._counter = Counter(self._cfg)

        # Avisar al ESP32 que el pipeline esta activo
        self._enviar_estado("LISTO")

        self._activo = True

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

        # Tiempo del ultimo envio UART para respetar el intervalo
        self._t_ultimo_envio = time.time()

        # Manejo de senal para apagado limpio
        signal.signal(signal.SIGTERM, self._apagar)
        signal.signal(signal.SIGINT,  self._apagar)

    def _iniciar_uart(self):
        """Abre el puerto serial. Devuelve None si falla."""
        try:
            uart = serial.Serial(self._uart_puerto, self._uart_baud, timeout=1)
            print(f"  [Engine] UART listo en {self._uart_puerto} a {self._uart_baud} baud.")
            return uart
        except Exception as e:
            print(f"  [Engine] Advertencia: no se pudo abrir UART ({e}). Corriendo sin serial.")
            return None

    def run(self):
        """Bucle principal: lee frame -> Tracker -> Counter -> UART (segun intervalo)."""
        print(f"[Engine] Modo 2 activo. Intervalo UART: {self._intervalo}s  Ctrl+C para detener.")

        while self._activo:
            ret, frame = self._captura.leer()
            if not ret or frame is None:
                if not self._captura.activo:
                    print("[Engine] Camara desconectada, cerrando.")
                    break
                continue

            # Pipeline de vision
            objetos = self._tracker.trackear(frame)
            self._counter.actualizar(objetos)

            # Enviar UART solo si paso el intervalo configurado
            t_now = time.time()
            if t_now - self._t_ultimo_envio >= self._intervalo:
                conteos = self._counter.get_conteos()
                self._enviar_uart(conteos)
                self._t_ultimo_envio = t_now

        self._cerrar()

    def _enviar_estado(self, estado: str):
        """
        Manda un mensaje de estado al ESP32.
        Formato: $ESTADO\n

        Estados usados:
            $CARGANDO  -- el engine esta iniciando, el modelo aun no cargo
            $LISTO     -- el pipeline esta activo y contando
        """
        if self._uart is None:
            return
        try:
            self._uart.write(f"${estado}\n".encode("ascii"))
        except Exception as e:
            print(f"  [Engine] Error UART estado: {e}")

    def _enviar_uart(self, conteos: dict):
        """
        Serializa los 6 conteos y los manda por UART.

        Formato: #p_acu_in,p_acu_out,p_aforo,v_acu_in,v_acu_out,v_aforo\n

        Donde:
            p_acu_in, p_acu_out, v_acu_in, v_acu_out -- solo crecen
            p_aforo, v_aforo                          -- pueden bajar o ser negativos

        El ESP32 puede calcular deltas de cualquier intervalo
        restando valores consecutivos de p_aforo o v_aforo.
        """
        if self._uart is None:
            return

        mensaje = (
            f"#{conteos['p_acu_in']},"
            f"{conteos['p_acu_out']},"
            f"{conteos['p_aforo']},"
            f"{conteos['v_acu_in']},"
            f"{conteos['v_acu_out']},"
            f"{conteos['v_aforo']}\n"
        )

        try:
            self._uart.write(mensaje.encode("ascii"))
        except Exception as e:
            print(f"  [Engine] Error UART: {e}")

    def _apagar(self, signum=None, frame=None):
        """Manejador de SIGTERM y SIGINT para apagado limpio del engine."""
        print("\n[Engine] Senal de apagado recibida, cerrando...")
        self._activo = False

    def apagado_sistema(self):
        """
        Cierra el engine limpiamente y luego apaga el sistema operativo.
        Llamado por ReceptorUART al recibir el comando !APAGAR del ESP32.

        Secuencia:
            1. Detiene el bucle principal poniendo _activo = False
            2. _cerrar() libera camara y UART (llamado al salir de run())
            3. subprocess ejecuta shutdown para apagar la Pi

        Nota: requiere permiso sudo sin contrasena para shutdown.
        Agregar en /etc/sudoers:
            pi ALL=(ALL) NOPASSWD: /sbin/shutdown
        """
        print("\n[Engine] Comando !APAGAR recibido. Iniciando apagado del sistema...")
        self._activo = False
        # _cerrar() se ejecuta al salir del bucle run(), luego apagamos
        # Usamos un hilo para dar tiempo a que run() termine antes del shutdown
        threading.Thread(target=self._shutdown_diferido, daemon=True).start()

    def _shutdown_diferido(self):
        """Espera a que el engine cierre y luego ejecuta shutdown."""
        time.sleep(2)  # tiempo para que run() salga y _cerrar() termine
        print("[Engine] Apagando sistema operativo...")
        subprocess.run(["sudo", "shutdown", "-h", "now"])

    def _cerrar(self):
        """Libera todos los recursos."""
        if self._receptor is not None:
            self._receptor.detener()
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
