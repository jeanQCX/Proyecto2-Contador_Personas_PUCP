# counter.py
# Clase Counter: determina si un objeto cruzo la linea de conteo
# y actualiza los conteos de personas y vehiculos.
# Depende de geometry.py para la logica de cruce.
# Recibe la lista de objetos de tracker.py.

import numpy as np
from geometry import detectar_cruce, linea_desde_config, linea_paralela, _signo_lado
from config_manager import ConfigManager

# ---------------------------------------------------------------------------
# Parametros de robustez - ajustar aqui para calibrar el sistema
# ---------------------------------------------------------------------------

# Frames sin ver un ID antes de eliminarlo del estado.
# Debe ser >= track_buffer de bytetrack.yaml o el personalizado
BUFFER_LIMPIEZA = 20

# Tipo de filtro para suavizar el centroide.
# Opciones: "kalman" | "ema" | "ninguno"
# kalman  -> mas robusto, maneja parpadeos de bbox, modela velocidad
# ema     -> mas simple, suavizado exponencial, sin modelado de velocidad
# ninguno -> sin filtro, comportamiento original
FILTRO = "kalman"

# --- Parametros EMA ---
# Alpha: peso del centroide actual vs el estado acumulado.
# 1.0 = sin filtro, 0.0 = nunca se mueve. Rango util: 0.2 a 0.5
EMA_ALPHA = 0.3

# --- Parametros Kalman ---
# Q: ruido de proceso. Confianza en el modelo cinematico (posicion + velocidad).
#    Representa cuanto se confia en la trayectoria estimada anteriormente.
#    Menor -> mas inercia, trayectoria mas suave, ignora cambios bruscos,
#             pero tarda mas en adaptarse a movimientos reales.
#    Mayor -> sigue mas rapido los cambios del centroide, pero puede seguir ruido.
#    Para personas: usar valores bajos porque el centroide puede tener saltos
#                   debido a cambios de bbox, oclusiones y detecciones inestables.
#    Rango tipico: 0.01 a 1.0
KALMAN_Q = 0.05


# R: ruido de medicion. Desconfianza en el centroide crudo del bbox.
#    Representa cuanto se cree en la medicion entregada por YOLO/ByteTrack.
#    Mayor -> se ignoran mas los saltos bruscos del centroide y se prioriza
#             la trayectoria estimada por Kalman.
#    Menor -> se sigue mas al centroide detectado, con menos suavizado.
#    Para personas: usar valores altos porque la posicion del bbox puede variar
#                   aunque la persona realmente no se haya movido.
#    Rango tipico: 1.0 a 100.0
KALMAN_R = 50

# --- Metodo de confirmacion ---
# Opciones: "n_frames" | "doble_linea" | "ninguno"
# n_frames    -> el cruce se confirma tras N frames consecutivos del lado destino
# doble_linea -> el cruce se confirma cuando el objeto atraviesa una segunda
#                linea paralela, desplazada ANCHO_BANDA_PX hacia cada lado
# ninguno     -> sin confirmacion, el primer cruce detectado ya cuenta
#METODO_CONFIRMACION = "n_frames"
METODO_CONFIRMACION = "doble_linea"

# Para METODO_CONFIRMACION = "n_frames":
# A 20 FPS: N=3 -> 0.15s latencia | N=5 -> 0.25s | N=8 -> 0.4s
N_FRAMES_CONFIRMACION = 1

# Para METODO_CONFIRMACION = "doble_linea":
# Distancia en pixeles desde la linea del usuario hasta cada linea de
# confirmacion paralela. El objeto debe recorrer esta distancia hacia el
# lado destino para que el cruce cuente. Es un umbral espacial, no temporal:
# no depende de la velocidad del objeto ni del FPS de la camara.
# Calibrar segun la resolucion de camara, valor tipico 15-40px en 640x480.
ANCHO_BANDA_PX = 15


# ---------------------------------------------------------------------------
# Filtro EMA para centroide 2D
# ---------------------------------------------------------------------------

class FiltroEMA:
    """
    Filtro de media exponencial movil (Exponential Moving Average) para
    suavizar la posicion del centroide de un objeto a lo largo del tiempo.

    Cada frame, el estado se actualiza como:
        x_nueva = alpha * x_cruda + (1 - alpha) * x_anterior
        y_nueva = alpha * y_cruda + (1 - alpha) * y_anterior

    Con alpha < 1, los saltos bruscos del centroide quedan atenuados porque
    el estado anterior "pesa" y tira hacia la trayectoria previa.

    Limitacion vs Kalman: no modela velocidad, entonces si el bbox parpadea
    un frame y reaparece desplazado, el EMA lo sigue sin amortiguar tanto
    como lo haria el Kalman (que predice donde deberia estar).
    """

    def __init__(self, cx: float, cy: float):
        # Estado inicial: la primera medicion cruda
        self._x = cx
        self._y = cy

    def update(self, cx: float, cy: float):
        """Actualiza el estado con el centroide crudo del frame actual."""
        self._x = EMA_ALPHA * cx + (1.0 - EMA_ALPHA) * self._x
        self._y = EMA_ALPHA * cy + (1.0 - EMA_ALPHA) * self._y

    def predict(self):
        """
        Llamado cuando el bbox no aparece en el frame (parpadeo).
        El EMA no tiene modelo de movimiento, entonces simplemente
        mantiene el estado actual sin cambiarlo.
        Existe para tener la misma interfaz que FiltroKalman.
        """
        pass  # EMA no predice, mantiene la ultima posicion filtrada

    def get_pos(self) -> tuple:
        return (self._x, self._y)


# ---------------------------------------------------------------------------
# Filtro de Kalman para centroide 2D
# ---------------------------------------------------------------------------

class FiltroKalman:
    """
    Filtro de Kalman para suavizar la trayectoria del centroide de un objeto.

    Estado interno: [x, y, vx, vy]
        x, y   -> posicion estimada del centroide
        vx, vy -> velocidad estimada en pixeles/frame

    El filtro tiene dos pasos por frame:
        predict() -> proyecta el estado al siguiente frame usando el modelo cinematico
        update()  -> corrige la prediccion con la medicion real del centroide

    Cuando el bbox parpadea (desaparece un frame), se llama solo predict()
    sin update(). El filtro estima donde deberia estar el objeto segun su
    velocidad, evitando la teleportacion cuando reaparece.

    Matrices del sistema (dt=1 frame):
        F (transicion de estado):
            [[1, 0, 1, 0],   x_nueva  = x + vx
             [0, 1, 0, 1],   y_nueva  = y + vy
             [0, 0, 1, 0],   vx_nueva = vx  (velocidad constante entre frames)
             [0, 0, 0, 1]]   vy_nueva = vy

        H (observacion): solo medimos posicion, no velocidad
            [[1, 0, 0, 0],
             [0, 1, 0, 0]]

        Q (ruido de proceso): KALMAN_Q * identidad
        R (ruido de medicion): KALMAN_R * identidad
    """

    def __init__(self, cx: float, cy: float):
        # Estado: [x, y, vx, vy] como columna (4x1)
        self.x = np.array([[cx], [cy], [0.0], [0.0]], dtype=float)

        # Covarianza inicial: alta incertidumbre en velocidad, baja en posicion
        self.P = np.diag([10.0, 10.0, 100.0, 100.0])

        # Modelo cinematico: posicion += velocidad * dt, dt=1 frame
        self.F = np.array([[1, 0, 1, 0],
                            [0, 1, 0, 1],
                            [0, 0, 1, 0],
                            [0, 0, 0, 1]], dtype=float)

        # Solo observamos x e y del estado [x, y, vx, vy]
        self.H = np.array([[1, 0, 0, 0],
                            [0, 1, 0, 0]], dtype=float)

        self.Q = np.eye(4) * KALMAN_Q
        self.R = np.eye(2) * KALMAN_R

    def predict(self):
        """
        Proyecta el estado al siguiente frame.
        Se llama aunque no haya medicion (bbox parpadeando).
        """
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, cx: float, cy: float):
        """
        Corrige la prediccion con la medicion real.
        La ganancia K pondera cuanto peso darle a la medicion vs la prediccion.
        Con R grande (desconfianza en el bbox), K es pequena y prevalece la prediccion.
        """
        z = np.array([[cx], [cy]], dtype=float)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ self.H) @ self.P

    def get_pos(self) -> tuple:
        return (float(self.x[0, 0]), float(self.x[1, 0]))


# ---------------------------------------------------------------------------
# Clase Counter
# ---------------------------------------------------------------------------

class Counter:
    """
    Procesa los objetos trackeados y cuenta cruces de linea.

    Pipeline por frame, en orden:
        1. Filtrado del centroide (Kalman o EMA segun FILTRO)
        2. detectar_cruce con epsilon=0 sobre el centroide filtrado
        3. Confirmacion por N frames antes de registrar el cruce

    El epsilon esta desactivado (=0) porque el filtro de centroide y la
    confirmacion N-frames cubren todos los casos de ruido de bbox.
    El epsilon generaba conflictos con la logica de confirmacion.
    """

    def __init__(self, cfg: ConfigManager):
        self._linea_personas  = linea_desde_config(cfg.get("linea_personas",  {}))
        self._linea_vehiculos = linea_desde_config(cfg.get("linea_vehiculos", {}))

        # Lineas paralelas de confirmacion para el metodo "doble_linea".
        # Se generan una sola vez aqui, no en cada frame, porque la linea
        # del usuario no cambia durante la ejecucion.
        # _lineas_confirmacion[tipo] = (linea_in, linea_out)
        #   linea_in  -> linea paralela desplazada ANCHO_BANDA_PX hacia p3
        #   linea_out -> linea paralela desplazada ANCHO_BANDA_PX al lado opuesto
        self._lineas_confirmacion = {
            "persona":  self._generar_lineas_confirmacion(self._linea_personas),
            "vehiculo": self._generar_lineas_confirmacion(self._linea_vehiculos),
        }

        aforo = cfg.get("aforo", {})
        self._max_personas     = aforo.get("max_personas",    100)
        self._max_vehiculos    = aforo.get("max_vehiculos",   100)
        self._offset_personas  = int(aforo.get("offset_personas",  0))
        self._offset_vehiculos = int(aforo.get("offset_vehiculos", 0))

        # Epsilon para banda de histeresis en pixeles, leido del config.
        # En config.json deberia ser 0.0 para ambos: el filtro de centroide
        # y la confirmacion (n_frames o doble_linea) reemplazan su funcion.
        # Se mantiene como legacy: si en el futuro se necesita reactivar,
        # solo se sube el valor en config.json sin tocar codigo.
        modelo = cfg.get("modelo", {})
        self._epsilon_personas  = modelo.get("epsilon_personas",  0.0)
        self._epsilon_vehiculos = modelo.get("epsilon_vehiculos", 0.0)

        # Contadores acumulados: solo suben
        self._p_acu_in  = 0
        self._p_acu_out = 0
        self._v_acu_in  = 0
        self._v_acu_out = 0

        # Estado confirmado por ID: {track_id: "in" | "out"}
        # Solo se actualiza cuando el cruce supera la confirmacion elegida
        self._estado_ids = {}

        # Frames sin ver cada ID para limpieza
        self._frames_ausente = {}

        # Filtros de centroide por ID: {track_id: FiltroKalman | FiltroEMA | None}
        # None cuando FILTRO = "ninguno"
        self._filtros = {}

        # Posicion FILTRADA del frame anterior por ID: {track_id: (x, y)}
        # CRITICO: detectar_cruce debe comparar filtrado-anterior vs filtrado-actual,
        # nunca crudo-anterior vs filtrado-actual. Mezclar esos dos genera resultados
        # invertidos o inconsistentes porque son dos series temporales distintas
        # (el filtro tiene retraso de fase respecto al centroide crudo).
        self._pos_filtrada_anterior = {}

        # Pendientes de confirmacion: {track_id: {"direccion": str, "frames": int}}
        # Usado solo con METODO_CONFIRMACION = "n_frames".
        self._pendientes = {}

        # Zona actual por ID para el metodo "doble_linea":
        # {track_id: "in_confirmado" | "out_confirmado" | "neutral"}
        # Se actualiza cada frame segun en que lado de cada linea paralela
        # esta el centroide filtrado. El cruce se registra cuando la zona
        # cambia de "neutral" a "in_confirmado" o "out_confirmado".
        self._zona_ids = {}

        if self._linea_personas is None:
            print("  [Counter] Advertencia: linea_personas no configurada.")
        if self._linea_vehiculos is None:
            print("  [Counter] Advertencia: linea_vehiculos no configurada.")

        print(f"  [Counter] Listo. filtro={FILTRO} "
              f"metodo_confirmacion={METODO_CONFIRMACION} "
              f"N_frames={N_FRAMES_CONFIRMACION} "
              f"ancho_banda={ANCHO_BANDA_PX}px "
              f"offset_p={self._offset_personas} "
              f"offset_v={self._offset_vehiculos}")

    # ------------------------------------------------------------------
    # Interfaz publica
    # ------------------------------------------------------------------

    def actualizar(self, objetos: list):
        """
        Procesa la lista de objetos trackeados del frame actual.
        """
        ids_activos = {obj["track_id"] for obj in objetos}

        # Para IDs vivos pero ausentes este frame (parpadeo de bbox):
        # llamar predict() para que el filtro mantenga estimacion coherente.
        # El EMA no hace nada en predict(), el Kalman avanza segun velocidad.
        for track_id, filtro in self._filtros.items():
            if track_id not in ids_activos and filtro is not None:
                filtro.predict()

        self._limpiar_ids_ausentes(ids_activos)

        for obj in objetos:
            track_id   = obj["track_id"]
            tipo       = obj["tipo"]
            pos_actual = obj["pos_actual"]   # centroide crudo del tracker

            # --- Paso 1: filtrado del centroide ---
            if track_id not in self._filtros:
                # Primera vez que vemos este ID: crear filtro e inicializar.
                # Tambien sembramos la posicion filtrada anterior con el mismo
                # punto, porque no hay frame previo con el que comparar todavia.
                self._filtros[track_id] = self._crear_filtro(pos_actual)
                self._pos_filtrada_anterior[track_id] = pos_actual

                # Si el metodo es doble_linea, sembrar la zona inicial real
                # del objeto (no asumir "neutral"). Un objeto puede aparecer
                # en camara ya dentro de una zona confirmada (ej: entro al
                # campo de vision pasada la linea), y eso NO debe contar
                # como un cruce, porque nunca hizo la transicion real.
                if METODO_CONFIRMACION == "doble_linea":
                    self._zona_ids[track_id] = self._calcular_zona(tipo, pos_actual)

                continue

            filtro = self._filtros[track_id]

            if filtro is not None:
                filtro.predict()
                filtro.update(pos_actual[0], pos_actual[1])
                pos_filtrada = filtro.get_pos()
            else:
                # Modo "ninguno": usar centroide crudo directamente.
                # Aqui pos_filtrada == pos_actual, entonces el comportamiento
                # es identico al codigo original (crudo vs crudo).
                pos_filtrada = pos_actual

            # CRITICO: comparamos filtrado-anterior vs filtrado-actual, ambos
            # de la MISMA naturaleza (misma serie temporal procesada). Nunca
            # mezclar crudo con filtrado: el filtro tiene retraso de fase
            # respecto al crudo, y comparar series distintas invierte o
            # corrompe el signo del cruce detectado.
            pos_filtrada_anterior = self._pos_filtrada_anterior[track_id]

            if tipo == "persona":
                linea = self._linea_personas
            else:
                linea = self._linea_vehiculos

            if linea is None:
                # Igual hay que actualizar el historial filtrado para el
                # siguiente frame, aunque no haya linea configurada.
                self._pos_filtrada_anterior[track_id] = pos_filtrada
                continue

            # --- Paso 2 y 3: deteccion + confirmacion, segun el metodo elegido ---
            if METODO_CONFIRMACION == "doble_linea":
                self._procesar_doble_linea(track_id, tipo, pos_filtrada)
            else:
                # "n_frames" o "ninguno" usan deteccion clasica sobre la
                # linea original del usuario, con epsilon legacy del config.
                p1, p2, p3 = linea
                epsilon = self._epsilon_personas if tipo == "persona" else self._epsilon_vehiculos
                resultado = detectar_cruce(pos_filtrada_anterior, pos_filtrada, p1, p2, p3, epsilon_px=epsilon)

                direccion_detectada = None
                if resultado == 1:
                    direccion_detectada = "in"
                elif resultado == -1:
                    direccion_detectada = "out"

                if METODO_CONFIRMACION == "ninguno":
                    # Sin confirmacion: el primer cruce detectado ya cuenta
                    if direccion_detectada is not None:
                        self._confirmar_cruce(track_id, tipo, direccion_detectada)
                else:
                    # "n_frames"
                    self._procesar_confirmacion_nframes(track_id, tipo, direccion_detectada,
                                                         pos_filtrada, p1, p2, p3)

            # Guardar la posicion filtrada de este frame para usarla como
            # "anterior" en el siguiente frame. Debe ser lo ultimo que se
            # hace con este ID en este frame.
            self._pos_filtrada_anterior[track_id] = pos_filtrada

    def get_conteos(self) -> dict:
        return {
            "p_acu_in":  self._p_acu_in,
            "p_acu_out": self._p_acu_out,
            "p_aforo":   self._p_acu_in - self._p_acu_out + self._offset_personas,
            "v_acu_in":  self._v_acu_in,
            "v_acu_out": self._v_acu_out,
            "v_aforo":   self._v_acu_in - self._v_acu_out + self._offset_vehiculos,
        }

    def get_centroides_filtrados(self) -> dict:
        """
        Devuelve la posicion filtrada actual de cada ID activo.
        Solo para debug visual (main_debug.py).

        Con FILTRO="ninguno" el filtro guardado es None, entonces no hay
        posicion propia que devolver: en ese caso este metodo no incluye
        ese ID, porque no existe centroide filtrado, es el mismo crudo.
        main_debug.py debe asumir que si el ID no aparece aqui, el punto
        filtrado coincide con el punto crudo del tracker.

        Devuelve:
            {track_id: (x, y)} solo para IDs con filtro Kalman o EMA activo.
        """
        resultado = {}
        for track_id, filtro in self._filtros.items():
            if filtro is not None:
                resultado[track_id] = filtro.get_pos()
        return resultado

    def get_lineas_confirmacion(self) -> dict:
        """
        Devuelve las lineas paralelas usadas por METODO_CONFIRMACION = "doble_linea".
        Solo para debug visual (main_debug.py), para dibujarlas en pantalla.

        Devuelve None si METODO_CONFIRMACION no es "doble_linea", o si la
        linea de un tipo no esta configurada.

        Devuelve:
            {
                "persona":  (linea_in, linea_out) | None,
                "vehiculo": (linea_in, linea_out) | None,
            }
            donde cada linea_in/linea_out es una tupla (p1, p2, p3) lista
            para pasar a las funciones de dibujo que ya usan ese formato.
        """
        if METODO_CONFIRMACION != "doble_linea":
            return {"persona": None, "vehiculo": None}
        return dict(self._lineas_confirmacion)

    def reset(self):
        self._p_acu_in  = 0
        self._p_acu_out = 0
        self._v_acu_in  = 0
        self._v_acu_out = 0
        self._estado_ids.clear()
        self._frames_ausente.clear()
        self._filtros.clear()
        self._pos_filtrada_anterior.clear()
        self._pendientes.clear()
        self._zona_ids.clear()
        print("  [Counter] Conteos reiniciados.")

    # ------------------------------------------------------------------
    # Privados
    # ------------------------------------------------------------------

    def _crear_filtro(self, pos_actual: tuple):
        """Fabrica el filtro correcto segun la constante FILTRO."""
        if FILTRO == "kalman":
            return FiltroKalman(pos_actual[0], pos_actual[1])
        elif FILTRO == "ema":
            return FiltroEMA(pos_actual[0], pos_actual[1])
        else:
            return None  # modo "ninguno"

    def _generar_lineas_confirmacion(self, linea):
        """
        A partir de (p1, p2, p3) genera las dos lineas paralelas usadas
        por el metodo de confirmacion "doble_linea".

        linea_in  -> desplazada ANCHO_BANDA_PX hacia el lado de p3 (entrada)
        linea_out -> desplazada ANCHO_BANDA_PX hacia el lado opuesto (salida)

        linea_paralela() de geometry.py no sabe hacia que lado es "hacia p3",
        solo devuelve un desplazamiento perpendicular segun el signo que se
        le pase. Aqui se prueba el signo positivo y se verifica con
        _signo_lado si quedo del mismo lado que p3; si no, se invierte.

        Devuelve None si la linea no esta configurada (linea es None).
        """
        if linea is None:
            return None

        p1, p2, p3 = linea

        # Probar con signo positivo
        q1, q2 = linea_paralela(p1, p2, ANCHO_BANDA_PX)
        punto_medio_q = ((q1[0] + q2[0]) / 2.0, (q1[1] + q2[1]) / 2.0)

        signo_q  = _signo_lado(p1, p2, punto_medio_q)
        signo_p3 = _signo_lado(p1, p2, p3)

        # Si el desplazamiento positivo quedo del mismo lado que p3, esa es
        # la linea "in". Si no, hay que usar el signo negativo para "in" y
        # el positivo pasa a ser "out".
        if (signo_q * signo_p3) > 0:
            linea_in  = (q1, q2, p3)
            qo1, qo2  = linea_paralela(p1, p2, -ANCHO_BANDA_PX)
            linea_out = (qo1, qo2, p3)
        else:
            linea_out = (q1, q2, p3)
            qi1, qi2  = linea_paralela(p1, p2, -ANCHO_BANDA_PX)
            linea_in  = (qi1, qi2, p3)

        return (linea_in, linea_out)

    def _procesar_confirmacion_nframes(self, track_id: int, tipo: str,
                                        direccion_detectada,
                                        pos_filtrada: tuple,
                                        p1: tuple, p2: tuple, p3: tuple):
        """
        Logica de confirmacion por N frames (METODO_CONFIRMACION = "n_frames").

        Sin epsilon, la deteccion es binaria: cruzo o no cruzo.
        Entonces solo hay dos casos por frame:

        Caso A - hay cruce detectado (direccion_detectada != None):
            - Si la direccion coincide con el estado ya confirmado -> ignorar
            - Si hay pendiente de la misma direccion -> avanzar contador
            - Si no hay pendiente o es direccion distinta -> nuevo pendiente
            - Si el contador llega a N -> confirmar y limpiar pendiente

        Caso B - no hay cruce detectado:
            - Si hay pendiente, verificar si el objeto sigue del lado destino
              usando el signo del centroide filtrado respecto a la linea.
              Si sigue del mismo lado -> avanzar contador (esta en zona cruzada
              pero no hay evento de cruce porque ya estaba ahi el frame anterior)
              Si volvio al lado origen -> cancelar pendiente

        El Caso B es necesario porque detectar_cruce solo devuelve cruce en el
        momento exacto en que el centroide cambia de lado. Los frames siguientes,
        el objeto ya esta del lado destino y no "cruza" de nuevo, pero necesitamos
        seguir contando frames para confirmar que realmente se quedo ahi.
        """
        estado_actual = self._estado_ids.get(track_id)
        pendiente     = self._pendientes.get(track_id)

        if direccion_detectada is not None:
            # Caso A: cruce detectado este frame

            if estado_actual == direccion_detectada:
                # Ya estaba confirmado en esa direccion, ignorar
                return

            if pendiente is not None and pendiente["direccion"] == direccion_detectada:
                pendiente["frames"] += 1
            else:
                # Pendiente nuevo o reemplaza uno de direccion contraria
                self._pendientes[track_id] = {"direccion": direccion_detectada, "frames": 1}
                pendiente = self._pendientes[track_id]

            if pendiente["frames"] >= N_FRAMES_CONFIRMACION:
                self._confirmar_cruce(track_id, tipo, direccion_detectada)
                del self._pendientes[track_id]

        else:
            # Caso B: no hay cruce detectado este frame
            if pendiente is None:
                return

            # Calcular de que lado esta el centroide filtrado ahora
            signo_actual = _signo_lado(p1, p2, pos_filtrada)
            signo_ref    = _signo_lado(p1, p2, p3)

            # Si signo_actual es 0, el punto esta exactamente sobre la linea:
            # no podemos determinar el lado, ignorar este frame sin cancelar
            if signo_actual == 0:
                return

            en_zona_positiva = (signo_ref * signo_actual) > 0
            lado_actual = "in" if en_zona_positiva else "out"

            if lado_actual == pendiente["direccion"]:
                # Sigue del lado destino: avanzar contador
                pendiente["frames"] += 1
                if pendiente["frames"] >= N_FRAMES_CONFIRMACION:
                    self._confirmar_cruce(track_id, tipo, pendiente["direccion"])
                    del self._pendientes[track_id]
            else:
                # Volvio al lado origen antes de confirmar: cancelar
                del self._pendientes[track_id]

    def _calcular_zona(self, tipo: str, pos: tuple) -> str:
        """
        Calcula en que zona esta un punto respecto a las dos lineas
        paralelas de confirmacion del tipo dado.

        Devuelve: "in_confirmado" | "out_confirmado" | "neutral"

        Si las lineas no estan configuradas para este tipo, devuelve
        "neutral" por seguridad (no deberia llamarse en ese caso, pero
        evita un crash si pasara).
        """
        lineas = self._lineas_confirmacion.get(tipo)
        if lineas is None:
            return "neutral"

        linea_in, linea_out = lineas
        p1_in,  p2_in,  p3_in  = linea_in
        p1_out, p2_out, p3_out = linea_out

        # cruzo_linea_in: True si el punto esta del MISMO lado que p3
        # respecto a linea_in. Esa linea esta desplazada hacia p3, entonces
        # estar del mismo lado que p3 significa que ya se adentro en la
        # zona de entrada confirmada.
        signo_in       = _signo_lado(p1_in, p2_in, pos)
        signo_in_ref   = _signo_lado(p1_in, p2_in, p3_in)
        cruzo_linea_in = (signo_in * signo_in_ref) > 0

        # cruzo_linea_out: True si el punto esta del lado OPUESTO a p3
        # respecto a linea_out. Esa linea esta desplazada al lado contrario
        # de p3, entonces estar del lado opuesto a p3 significa que ya se
        # adentro en la zona de salida confirmada.
        signo_out       = _signo_lado(p1_out, p2_out, pos)
        signo_out_ref   = _signo_lado(p1_out, p2_out, p3_out)
        cruzo_linea_out = (signo_out * signo_out_ref) < 0

        if cruzo_linea_in:
            return "in_confirmado"
        elif cruzo_linea_out:
            return "out_confirmado"
        else:
            return "neutral"

    def _procesar_doble_linea(self, track_id: int, tipo: str, pos_filtrada: tuple):
        """
        Logica de confirmacion espacial (METODO_CONFIRMACION = "doble_linea").

        En vez de contar frames, se evalua en que ZONA esta el centroide
        filtrado respecto a las dos lineas paralelas generadas en el init:

            zona "in_confirmado"  -> cruzo la linea_in  (entro ANCHO_BANDA_PX
                                      pixeles hacia el lado de p3)
            zona "out_confirmado" -> cruzo la linea_out (entro ANCHO_BANDA_PX
                                      pixeles hacia el lado opuesto a p3)
            zona "neutral"        -> esta entre ambas lineas, ni confirmado

        El cruce se registra solo en la TRANSICION de "neutral" hacia una
        zona confirmada. Si el objeto ya estaba en una zona confirmada y
        sigue ahi, no se repite el registro (equivalente a estado_actual
        en el metodo n_frames). Si pasa de una zona confirmada de vuelta
        a neutral, no se cuenta nada todavia: recien se cuenta cuando
        alcanza la zona confirmada opuesta.

        La zona inicial de cada ID se siembra con su zona REAL en el momento
        de su primera aparicion (ver actualizar()), no con "neutral" por
        defecto. Esto evita contar un cruce falso cuando un objeto aparece
        en camara ya dentro de una zona confirmada (entro al campo de
        vision pasada la linea, nunca hizo la transicion real).

        Esto es mas robusto que n_frames ante objetos de distinta velocidad
        porque el umbral es una DISTANCIA fija, no un tiempo fijo. Un carro
        rapido y una persona caminando necesitan recorrer la misma cantidad
        de pixeles para confirmar, sin importar cuantos frames les tome.
        """
        if self._lineas_confirmacion.get(tipo) is None:
            return  # linea no configurada para este tipo

        zona_actual   = self._calcular_zona(tipo, pos_filtrada)
        zona_anterior = self._zona_ids.get(track_id, "neutral")

        # Solo nos interesa la TRANSICION desde neutral hacia una zona
        # confirmada. Cualquier otro caso (ya estaba confirmado, o sigue
        # en neutral) no genera registro.
        if zona_anterior == "neutral" and zona_actual == "in_confirmado":
            self._confirmar_cruce(track_id, tipo, "in")
        elif zona_anterior == "neutral" and zona_actual == "out_confirmado":
            self._confirmar_cruce(track_id, tipo, "out")

        self._zona_ids[track_id] = zona_actual

    def _confirmar_cruce(self, track_id: int, tipo: str, direccion: str):
        """Registra el cruce como definitivo."""
        if self._estado_ids.get(track_id) == direccion:
            return  # doble verificacion por seguridad
        self._estado_ids[track_id] = direccion
        self._registrar(tipo, 1 if direccion == "in" else -1, track_id)

    def _limpiar_ids_ausentes(self, ids_activos: set):
        """
        Limpia IDs que ya no aparecen en el frame actual.

        Se itera sobre la union de todos los dicts que guardan estado por ID,
        no solo _estado_ids. Esto es necesario porque un objeto puede tener
        filtro Kalman/EMA y posicion filtrada anterior sin haber confirmado
        ningun cruce todavia (ej: un objeto que pasa por camara pero nunca
        llega a cruzar la linea). Si solo limpiaramos en base a _estado_ids,
        esos IDs quedarian acumulados en _filtros y _pos_filtrada_anterior
        para siempre, generando una fuga de memoria lenta.
        """
        ids_a_revisar = (set(self._estado_ids.keys())
                          | set(self._filtros.keys())
                          | set(self._pos_filtrada_anterior.keys())
                          | set(self._pendientes.keys())
                          | set(self._zona_ids.keys()))

        for track_id in ids_a_revisar:
            if track_id not in ids_activos:
                self._frames_ausente[track_id] = self._frames_ausente.get(track_id, 0) + 1
                if self._frames_ausente[track_id] >= BUFFER_LIMPIEZA:
                    self._estado_ids.pop(track_id, None)
                    self._frames_ausente.pop(track_id, None)
                    self._filtros.pop(track_id, None)
                    self._pos_filtrada_anterior.pop(track_id, None)
                    self._pendientes.pop(track_id, None)
                    self._zona_ids.pop(track_id, None)
            else:
                self._frames_ausente.pop(track_id, None)

    def _registrar(self, tipo: str, direccion: int, track_id: int):
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
