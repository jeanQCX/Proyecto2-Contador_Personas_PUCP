# Sistema Inteligente de Aforo :D

Guía de instalación para Raspberry Pi 4.

## Requisitos previos

- Raspberry Pi 4
- Raspberry Pi OS Lite 64-bit

### Configuración recomendada en Raspberry Pi Imager

| Parámetro | Valor |
|-----------|--------|
| Hostname | aforo |
| Usuario | pi |
| Contraseña | aforo |
| WiFi | Red disponible |
| SSH | Habilitado |
| VNC | Opcional |

---

## Paso 1 - Conectarse por SSH

```bash
ssh pi@aforo.local
```

Contraseña:

```text
aforo
```

---

## Paso 2 - Actualizar sistema

```bash
sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y
sudo reboot
```

La conexión SSH se cortará temporalmente debido al reinicio.

---

## Paso 3 - Reconectarse

```bash
ssh pi@aforo.local
```

---

## Paso 4 - Configurar acceso a GitHub

Generar clave SSH:

```bash
ssh-keygen -t ed25519 -C "pi@aforo"
```

Mostrar clave pública:

```bash
cat ~/.ssh/id_ed25519.pub
```

Agregar la clave en:

```text
GitHub → Settings → SSH and GPG Keys → New SSH Key
```

Verificar acceso:

```bash
ssh -T git@github.com
```

---

## Paso 5 - Crear directorio del proyecto

```bash
mkdir -p ~/proyecto_aforo
cd ~/proyecto_aforo
```

---

## Paso 6 - Verificar Internet

```bash
ping -c 4 github.com
```

---

## Paso 7 - Clonar repositorio

```bash
git clone git@github.com:jeanQCX/Proyecto2-Contador_Personas_PUCP.git
```

---

## Paso 8 - Preparar estructura

```bash
mv Proyecto2-Contador_Personas_PUCP/Proyecto_aforo_reducido_github_v3/* .
rm -rf Proyecto2-Contador_Personas_PUCP
```

Estructura esperada:

```text
~/proyecto_aforo/
├── aforo/
├── services/
├── instalar_dependencias.sh
├── instalar_servicios.sh
├── manual.sh
├── README.md
└── requirements.txt
```
---

## Paso 7 y 8 - Alternativo: solo clonar la carpeta del repo q quieres

```bash
git clone --no-checkout git@github.com:jeanQCX/Proyecto2-Contador_Personas_PUCP.git
cd Proyecto2-Contador_Personas_PUCP
git sparse-checkout init
git sparse-checkout set Proyecto_aforo_reducido_github_v3
git checkout main
```

---
## Paso 9 - Instalar dependencias

```bash
chmod +x instalar_dependencias.sh
./instalar_dependencias.sh
```

---

## Paso 10 - Instalar servicios

```bash
chmod +x instalar_servicios.sh
./instalar_servicios.sh
```

---

## Paso 11 - Reiniciar

```bash
sudo reboot
```

---

## Notas

Si se reinstala Raspberry Pi OS:

- La clave SSH se perderá.
- Se deben repetir los pasos anteriores.
- Es recomendable eliminar la clave antigua de GitHub antes de registrar la nueva.

- Como quedara al final el proyecto:
```text
/home/pi/proyecto_aforo/
│
├── instalar_dependencias.sh
├── instalar_servicios.sh
├── manual.sh
├── README.md
├── requirements.txt
│
├── aforo/
│   ├── best_256.pt
│   ├── best_320.pt
│   ├── best_640.pt
│   ├── boot_manager.py
│   ├── config.json
│   ├── config_manager.py
│   ├── counter.py
│   ├── geometry.py
│   ├── main.py
│   ├── main_debug.py
│   ├── my_botsort.yaml
│   ├── my_bytetrack.yaml
│   ├── tracker.py
│   │
│   ├── web/
│   │   ├── app.py
│   │   ├── static/
│   │   │   ├── app.js
│   │   │   ├── icon.png
│   │   │   └── style.css
│   │   │
│   │   └── templates/
│   │       └── index.html
│   │
│   └── yolo26n_rx256_ncnn_model/
│
└── services/
    ├── aforo-engine.service
    ├── aforo-web.service
    └── wlan-static-ip.service
```
