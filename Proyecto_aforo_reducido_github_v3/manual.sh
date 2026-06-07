#!/bin/bash
# manual.sh / Guia de instalacion del sistema de aforo
#
# Requisitos previos:
# - Raspberry Pi 4
# - Raspberry Pi OS Lite 64-bit
#
# Configuracion recomendada en Raspberry Pi Imager:
#   Hostname:    aforo
#   Usuario:     pi
#   Contrasena:  aforo
#   WiFi:        (la red disponible)
#   SSH:         habilitado
#   VNC:         opcional
#
# Una vez arrancada la Raspberry:
# seguir los pasos de este documento.
# ---------------------------------------------
# PASO 1 - Conectarse por SSH (desde tu PC)
# ---------------------------------------------
ssh pi@aforo.local
# contrasena: aforo

# ---------------------------------------------
# PASO 2 - Actualizar sistema
# ---------------------------------------------
sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y
sudo reboot
# la conexion SSH se corta, es normal

# ---------------------------------------------
# PASO 3 - Reconectarse luego del reboot
# ---------------------------------------------
ssh pi@aforo.local
# contrasena: aforo

# ---------------------------------------------
# PASO 4 - Generar llave SSH para GitHub
# ---------------------------------------------
ssh-keygen -t ed25519 -C "pi@aforo"
# presionar Enter en todo, sin passphrase

# Mostrar la llave publica
cat ~/.ssh/id_ed25519.pub
# copiar todo ese texto y pegarlo en:
# GitHub -> Settings -> SSH and GPG keys -> New SSH key -> pegar y guardar

# Verificar conexion con GitHub
ssh -T git@github.com
# respuesta esperada: Hi jeanQCX! You've successfully authenticated...

# ---------------------------------------------
# PASO 5 - Crear directorio principal
# ---------------------------------------------
mkdir -p ~/proyecto_aforo
cd ~/proyecto_aforo

# ---------------------------------------------
# PASO 6 - Clonar repositorio
# ---------------------------------------------
git clone git@github.com:jeanQCX/Proyecto2-Contador_Personas_PUCP.git

# ---------------------------------------------
# PASO 7 - Mover contenido util y limpiar
# ---------------------------------------------
mv Proyecto2-Contador_Personas_PUCP/Proyecto_aforo_reducido_github_v2/* .
rm -rf Proyecto2-Contador_Personas_PUCP

# estructura resultante:
# ~/proyecto_aforo/
# ├── aforo/
# ├── services/
# ├── instalar_dependencias.sh
# └── instalar_servicios.sh

# ---------------------------------------------
# PASO 8 - Ejecutar instalacion de dependencias
# ---------------------------------------------
chmod +x instalar_dependencias.sh
./instalar_dependencias.sh
# esto puede tardar varios minutos

# ---------------------------------------------
# PASO 9 - Instalar/Crear Servicios
# ---------------------------------------------
chmod +x instalar_servicios.sh
./instalar_servicios.sh

# ---------------------------------------------
# PASO 10 - Reboot final
# ---------------------------------------------
sudo reboot

# ---------------------------------------------
# NOTA: si re-flasheas la SD en el futuro
# ---------------------------------------------
# La llave SSH se pierde con la SD.
# Repetir pasos 1 al 9.
# En GitHub borrar la llave vieja antes de agregar la nueva:
# GitHub -> Settings -> SSH and GPG keys -> borrar la anterior