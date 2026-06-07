# counter.py
# Clase Counter: determina si un objeto cruzo la linea de conteo
# y actualiza los conteos de personas y vehiculos.
# Depende de geometry.py para la logica de cruce.
# Recibe la lista de objetos de tracker.py.
 
from geometry import detectar_cruce, linea_desde_config
from config_manager import ConfigManager
 
# Frames sin ver un ID antes de eliminarlo del estado
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
 
        # Contadores acumulables solo crecen, nunca negativos
        self._personas_in   = 0
        self._personas_out  = 0
        self._vehiculos_in  = 0
        self._vehiculos_out = 0
 
        # Deltas por frame se resetean cada llamada a actualizar()
        self._personas_delta_in   = 0
        self._personas_delta_out  = 0
        self._vehiculos_delta_in  = 0
        self._vehiculos_delta_out = 0
 
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
        y actualiza conteos y deltas.
 
        Los deltas se resetean al inicio de cada llamada -
        representan los cruces ocurridos en este frame unicamente.
 
        Parametros:
            objetos : lista de dicts devuelta por tracker.trackear()
        """
        # Resetear deltas del frame anterior
        self._personas_delta_in   = 0
        self._personas_delta_out  = 0
        self._vehiculos_delta_in  = 0
        self._vehiculos_delta_out = 0
 
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
            direccion = "in" if resultado == 1 else "out"
            estado_actual = self._estado_ids.get(track_id)
 
            if estado_actual == direccion:
                continue  # misma direccion que la ultima vez, ignorar
 
            # Registrar cruce y actualizar estado
            self._estado_ids[track_id] = direccion
            self._registrar(tipo, resultado, track_id)
            

    def get_conteos(self) -> dict:
        """
        Devuelve el estado completo del conteo para este frame.
 
        Variables acumulables (solo crecen, nunca negativas):
            personas_in, personas_out
            vehiculos_in, vehiculos_out
 
        Variables de aforo (pueden ser negativas):
            personas_aforo  = personas_in  - personas_out  + offset_personas
            vehiculos_aforo = vehiculos_in - vehiculos_out + offset_vehiculos
 
        Deltas por frame (cruces en este frame, nunca negativos):
            personas_delta_in, personas_delta_out
            vehiculos_delta_in, vehiculos_delta_out
 
        Delta de aforo por frame (puede ser negativo):
            personas_delta_aforo  = delta_in - delta_out
            vehiculos_delta_aforo = delta_in - delta_out
        """
        return {
            # Personas acumulables
            "personas_in":            self._personas_in,
            "personas_out":           self._personas_out,
            "personas_aforo":         self._personas_in - self._personas_out + self._offset_personas,
 
            # Personas delta por frame
            "personas_delta_in":      self._personas_delta_in,
            "personas_delta_out":     self._personas_delta_out,
            "personas_delta_aforo":   self._personas_delta_in - self._personas_delta_out,
 
            # Vehiculos acumulables
            "vehiculos_in":           self._vehiculos_in,
            "vehiculos_out":          self._vehiculos_out,
            "vehiculos_aforo":        self._vehiculos_in - self._vehiculos_out + self._offset_vehiculos,
 
            # Vehiculos delta por frame
            "vehiculos_delta_in":     self._vehiculos_delta_in,
            "vehiculos_delta_out":    self._vehiculos_delta_out,
            "vehiculos_delta_aforo":  self._vehiculos_delta_in - self._vehiculos_delta_out,
        }
 
    def reset(self):
        """
        Reinicia todos los conteos y deltas a cero.
        Los offsets del config no se restauran.
        """
        self._personas_in   = 0
        self._personas_out  = 0
        self._vehiculos_in  = 0
        self._vehiculos_out = 0
        self._personas_delta_in   = 0
        self._personas_delta_out  = 0
        self._vehiculos_delta_in  = 0
        self._vehiculos_delta_out = 0
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
        # Incrementar ausencia de IDs que no estan en este frame
        for track_id in list(self._estado_ids.keys()):
            if track_id not in ids_activos:
                self._frames_ausente[track_id] = self._frames_ausente.get(track_id, 0) + 1
                if self._frames_ausente[track_id] >= BUFFER_LIMPIEZA:
                    del self._estado_ids[track_id]
                    del self._frames_ausente[track_id]
            else:
                # Reaparecio - resetear contador
                self._frames_ausente.pop(track_id, None)
 
    def _registrar(self, tipo: str, direccion: int, track_id: int):
        """
        Registra un cruce en los contadores y deltas del frame.
        direccion: +1 entrada (in), -1 salida (out)
        in y out nunca bajan de cero.
        """
        if tipo == "persona":
            if direccion == 1:
                self._personas_in       += 1
                self._personas_delta_in += 1
                print(f"  [Counter] Persona  ID{track_id:3d} entro  | in:{self._personas_in:3d}  out:{self._personas_out:3d}  aforo:{self._personas_in - self._personas_out + self._offset_personas:3d}")
            else:
                self._personas_out       += 1
                self._personas_delta_out += 1
                print(f"  [Counter] Persona  ID{track_id:3d} salio  | in:{self._personas_in:3d}  out:{self._personas_out:3d}  aforo:{self._personas_in - self._personas_out + self._offset_personas:3d}")
        else:
            if direccion == 1:
                self._vehiculos_in       += 1
                self._vehiculos_delta_in += 1
                print(f"  [Counter] Vehiculo ID{track_id:3d} entro  | in:{self._vehiculos_in:3d}  out:{self._vehiculos_out:3d}  aforo:{self._vehiculos_in - self._vehiculos_out + self._offset_vehiculos:3d}")
            else:
                self._vehiculos_out       += 1
                self._vehiculos_delta_out += 1
                print(f"  [Counter] Vehiculo ID{track_id:3d} salio  | in:{self._vehiculos_in:3d}  out:{self._vehiculos_out:3d}  aforo:{self._vehiculos_in - self._vehiculos_out + self._offset_vehiculos:3d}")
                
