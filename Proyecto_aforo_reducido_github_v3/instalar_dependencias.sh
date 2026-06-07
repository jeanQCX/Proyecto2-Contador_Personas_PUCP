#!/bin/bash
# instalar_dependencias.sh
# Crea el venv afov e instala todas las dependencias del proyecto.
# Ejecutar desde ~/proyecto_aforo/

set -e  # detener si cualquier comando falla

echo "=== [1/4] Instalando dependencias del sistema ==="
sudo apt install -y python3 python3-pip python3-venv python3-dev

echo "=== [2/4] Creando entorno virtual afov ==="
python3 -m venv afov

echo "=== [3/4] Activando venv e instalando librerias ==="
source ~/proyecto_aforo/afov/bin/activate
pip install --upgrade pip
pip install --prefer-binary \
    opencv-python \
    pyserial \
    RPi.GPIO \
    numpy \
    flask \
    ultralytics

echo "=== [4/4] Listo ==="
echo "Venv creado en ~/proyecto_aforo/afov"
echo "Para activarlo manualmente: source ~/proyecto_aforo/afov/bin/activate"