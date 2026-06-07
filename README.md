# Sistema Inteligente de Aforo

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
mv Proyecto2-Contador_Personas_PUCP/Proyecto_aforo_reducido_github_v2/* .
rm -rf Proyecto2-Contador_Personas_PUCP
```

Estructura esperada:

```text
~/proyecto_aforo/
├── aforo/
├── services/
├── instalar_dependencias.sh
└── instalar_servicios.sh
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
