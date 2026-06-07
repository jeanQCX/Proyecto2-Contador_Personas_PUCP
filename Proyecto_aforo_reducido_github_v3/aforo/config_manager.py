import os
import json

class ConfigManager:
    """
    Clase encargada de toda la lectura y escritura del config.json.
    Los demas .py no tocan el archivo directamente,
    solo usan get() y set() de esta clase.
    """

    TEMPLATE = {
    "linea_personas": {
        "p1": None,
        "p2": None,
        "p3": None
    },
    "linea_vehiculos": {
        "p1": None,
        "p2": None,
        "p3": None
    },
    "roi": {
        "p1": None,
        "p2": None
    },
    "aforo": {
        "max_personas":    100,
        "max_vehiculos":   100,
        "offset_personas": 0,
        "offset_vehiculos": 0
    },
    "modelo": {
        "confianza": 0.5,
        "iou":       0.4,
        "epsilon_personas": 2.0,
        "epsilon_vehiculos": 4.0
    },
    "camara": {
        "indice": 0,
        "ancho":  640,
        "alto":   480
    },
    "uart": {
    "puerto":    "/dev/ttyS0",
    "baudrate":  115200,
    "intervalo": 1.0
    },
    "red": {
        "ssid":     "aforo-config",
        "password": "12345678"
    }
    }

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, "config.json")
        self._config = self._cargar()

    def _cargar(self):
        """
        Lee el config.json del disco.
        Si no existe o esta vacio, crea el archivo con el template
        por defecto y lo retorna.
        """
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                contenido = f.read().strip()
                if contenido:
                    return json.loads(contenido)

        # Archivo no existe o estaba vacio: usar template
        print("  [ConfigManager] config.json no encontrado o vacio, creando con template por defecto.")
        with open(self.config_path, "w") as f:
            json.dump(self.TEMPLATE, f, indent=4)
        return dict(self.TEMPLATE)

    def _guardar(self):
        """
        Escribe el estado actual de self._config al disco.
        Se llama automaticamente despues de cada set() o reset().
        """
        with open(self.config_path, "w") as f:
            json.dump(self._config, f, indent=4)

    def get(self, clave, default=None):
        """
        Devuelve el valor asociado a la clave.
        Si la clave no existe, devuelve default (None por defecto).

        Ejemplo:
            linea = cfg.get("linea")
            confianza = cfg.get("confianza", 0.5)
        """
        return self._config.get(clave, default)

    def set(self, clave, valor):
        """
        Guarda o actualiza un valor en memoria y luego en disco.

        Ejemplo:
            cfg.set("linea", {"p1": [100, 200], "p2": [400, 200]})
            cfg.set("confianza", 0.5)
        """
        self._config[clave] = valor
        self._guardar()
        print(f"  [ConfigManager] '{clave}' guardado en {self.config_path}")

    def reset(self, clave):
        """
        Elimina una clave especifica del config.
        Si la clave no existe, no hace nada.

        Ejemplo:
            cfg.reset("linea")
        """
        if clave in self._config:
            del self._config[clave]
            self._guardar()
            print(f"  [ConfigManager] '{clave}' eliminado.")
        else:
            print(f"  [ConfigManager] '{clave}' no existe, nada que eliminar.")

    def reset_todo(self):
        """
        Restaura el config.json al template por defecto.
        Util si quieres empezar de cero.
        """
        self._config = dict(self.TEMPLATE)
        self._guardar()
        print("  [ConfigManager] config.json restaurado al template por defecto.")

    def get_todo(self):
        """
        Devuelve una copia de toda la config en memoria.
        Util para debug.
        """
        return dict(self._config)


if __name__ == "__main__":
    cfg = ConfigManager()

    # Prueba set
    cfg.set("confianza", 0.5474)
    cfg.set("iou", 0.4788)
    cfg.set("linea", {"p1": [100, 200], "p2": [400, 200]})

    # Prueba get
    print(cfg.get("confianza"))
    print(cfg.get("linea"))
    print(cfg.get("no_existe", "valor_por_defecto"))

    # Prueba get_todo
    print(cfg.get_todo())

    # Prueba reset
    cfg.reset("iou")
    print(cfg.get_todo())
    
    cfg.reset_todo()
    print(cfg.get_todo())
