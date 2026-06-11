# counter.py
# Clase Counter: determina si un objeto cruzo la linea de conteo
# y actualiza los conteos de personas y vehiculos.
# Depende de geometry.py para la logica de cruce.
# Recibe la lista de objetos de tracker.py.

from geometry import detectar_cruce, linea_desde_config
from config_manager import ConfigManager

# Frames sin ver un ID antes de eliminarlo del estado.
# Debe ser >= track_buffer de bytetrack.yaml (default 30)
BUFFER_LIMPIEZA = 30


class Counter:
    """
    Procesa los objetos trackeados y cuenta cruces de linea.

    Uso tipico:
        cfg     = ConfigManager()
        counter = Counter(cfg)
        counter.actualizar(objetos)   # objetos viene de tracker.trackear()
        conteos = counter.get_conteos()
    """

    def __init__(self, cfg: ConfigManager):
        # Leer lineas del config
        self._linea_personas  = linea_desde_config(cfg.get("linea_personas",  {}))
        self._linea_vehiculos = linea_desde_config(cfg.get("linea_vehiculos", {}))

        # Leer aforo del config
        aforo = cfg.get("aforo", {})
        self._max_personas     = aforo.get("max_personas",    100)
        self._max_vehiculos    = aforo.get("max_vehiculos",   100)
        self._offset_personas  = int(aforo.get("offset_personas",  0))
        self._offset_vehiculos = int(aforo.get("offset_vehiculos", 0))

        # Epsilon para banda de histeresis en pixeles (separado por tipo)
        self._epsilon_personas  = cfg.get("modelo", {}).get("epsilon_personas", 2.0)
        self._epsilon_vehiculos = cfg.get("modelo", {}).get("epsilon_vehiculos", 4.0)

        # --- Contadores acumulados de flujo ---
        # Solo crecen, nunca bajan. Representan cruces totales desde el arranque.
        # El _ inicial es convencion Python para atributos privados:
        # no se acceden directamente desde fuera, solo via get_conteos().
        self._p_acu_in  = 0   # personas que entraron en total
        self._p_acu_out = 0   # personas que salieron en total
        self._v_acu_in  = 0   # vehiculos que entraron en total
        self._v_acu_out = 0   # vehiculos que salieron en total

        # Estado por ID: {track_id: "in" | "out"}
        # Controla que un ID no repita la misma direccion dos veces seguidas
        self._estado_ids = {}

        # Contador de frames sin ver cada ID para limpieza
        # {track_id: frames_ausente}
        self._frames_ausente = {}

        if self._linea_personas is None:
            print("  [Counter] Advertencia: linea_personas no configurada.")
        if self._linea_vehiculos is None:
            print("  [Counter] Advertencia: linea_vehiculos no configurada.")

        print(f"  [Counter] Listo. "
              f"offset_personas={self._offset_personas} "
              f"offset_vehiculos={self._offset_vehiculos} "
              f"epsilon_personas={self._epsilon_personas} "
              f"epsilon_vehiculos={self._epsilon_vehiculos}")

    # ------------------------------------------------------------------
    # Interfaz publica
    # ------------------------------------------------------------------

    def actualizar(self, objetos: list):
        """
        Procesa la lista de objetos trackeados del frame actual
        y actualiza los conteos acumulados.

        Parametros:
            objetos : lista de dicts devuelta por tracker.trackear()
        """
        # IDs activos en este frame
        ids_activos = {obj["track_id"] for obj in objetos}

        # Limpieza de IDs ausentes
        self._limpiar_ids_ausentes(ids_activos)

        for obj in objetos:
            track_id     = obj["track_id"]
            tipo         = obj["tipo"]
            pos_actual   = obj["pos_actual"]
            pos_anterior = obj["pos_anterior"]

            # Primera aparicion del ID, no hay trayectoria todavia
            if pos_anterior is None:
                continue

            # Seleccionar linea segun tipo
            if tipo == "persona":
                linea = self._linea_personas
            else:
                linea = self._linea_vehiculos

            # Linea no configurada, ignorar
            if linea is None:
                continue

            p1, p2, p3 = linea
            epsilon     = self._epsilon_personas if tipo == "persona" else self._epsilon_vehiculos
            resultado   = detectar_cruce(pos_anterior, pos_actual, p1, p2, p3, epsilon)

            if resultado == 0:
                continue

            # Verificar que la direccion sea valida segun estado del ID
            direccion     = "in" if resultado == 1 else "out"
            estado_actual = self._estado_ids.get(track_id)

            if estado_actual == direccion:
                continue  # misma direccion que la ultima vez, ignorar

            # Registrar cruce y actualizar estado
            self._estado_ids[track_id] = direccion
            self._registrar(tipo, resultado, track_id)

    def get_conteos(self) -> dict:
        """
        Devuelve el estado actual del conteo.

        Flujo acumulado (solo sube, nunca baja):
            p_acu_in   -- personas que entraron desde el arranque
            p_acu_out  -- personas que salieron desde el arranque
            v_acu_in   -- vehiculos que entraron desde el arranque
            v_acu_out  -- vehiculos que salieron desde el arranque

        Aforo actual (puede subir o bajar, puede ser negativo):
            p_aforo = p_acu_in - p_acu_out + offset_personas
            v_aforo = v_acu_in - v_acu_out + offset_vehiculos
        """
        return {
            "p_acu_in":  self._p_acu_in,
            "p_acu_out": self._p_acu_out,
            "p_aforo":   self._p_acu_in - self._p_acu_out + self._offset_personas,
            "v_acu_in":  self._v_acu_in,
            "v_acu_out": self._v_acu_out,
            "v_aforo":   self._v_acu_in - self._v_acu_out + self._offset_vehiculos,
        }

    def reset(self):
        """
        Reinicia todos los conteos a cero.
        Los offsets del config no se tocan.
        """
        self._p_acu_in  = 0
        self._p_acu_out = 0
        self._v_acu_in  = 0
        self._v_acu_out = 0
        self._estado_ids.clear()
        self._frames_ausente.clear()
        print("  [Counter] Conteos reiniciados.")

    # ------------------------------------------------------------------
    # Privados
    # ------------------------------------------------------------------

    def _limpiar_ids_ausentes(self, ids_activos: set):
        """
        Incrementa el contador de ausencia de cada ID que no esta en
        el frame actual. Si supera BUFFER_LIMPIEZA, lo elimina del estado.
        Si un ID reaparece, resetea su contador de ausencia.
        """
        for track_id in list(self._estado_ids.keys()):
            if track_id not in ids_activos:
                self._frames_ausente[track_id] = self._frames_ausente.get(track_id, 0) + 1
                if self._frames_ausente[track_id] >= BUFFER_LIMPIEZA:
                    del self._estado_ids[track_id]
                    del self._frames_ausente[track_id]
            else:
                self._frames_ausente.pop(track_id, None)

    def _registrar(self, tipo: str, direccion: int, track_id: int):
        """
        Registra un cruce en los contadores acumulados.
        direccion: +1 entrada (in), -1 salida (out)
        p_acu_in y p_acu_out nunca bajan de cero.
        """
        if tipo == "persona":
            if direccion == 1:
                self._p_acu_in += 1
                p_aforo = self._p_acu_in - self._p_acu_out + self._offset_personas
                print(f"  [Counter] Persona  ID{track_id:3d} entro  | "
                      f"acu_in:{self._p_acu_in:3d}  acu_out:{self._p_acu_out:3d}  aforo:{p_aforo:3d}")
            else:
                self._p_acu_out += 1
                p_aforo = self._p_acu_in - self._p_acu_out + self._offset_personas
                print(f"  [Counter] Persona  ID{track_id:3d} salio  | "
                      f"acu_in:{self._p_acu_in:3d}  acu_out:{self._p_acu_out:3d}  aforo:{p_aforo:3d}")
        else:
            if direccion == 1:
                self._v_acu_in += 1
                v_aforo = self._v_acu_in - self._v_acu_out + self._offset_vehiculos
                print(f"  [Counter] Vehiculo ID{track_id:3d} entro  | "
                      f"acu_in:{self._v_acu_in:3d}  acu_out:{self._v_acu_out:3d}  aforo:{v_aforo:3d}")
            else:
                self._v_acu_out += 1
                v_aforo = self._v_acu_in - self._v_acu_out + self._offset_vehiculos
                print(f"  [Counter] Vehiculo ID{track_id:3d} salio  | "
                      f"acu_in:{self._v_acu_in:3d}  acu_out:{self._v_acu_out:3d}  aforo:{v_aforo:3d}")
