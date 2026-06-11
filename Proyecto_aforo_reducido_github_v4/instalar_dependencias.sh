#!/bin/bash
# instalar_dependencias.sh
# Crea el venv afov e instala todas las dependencias del proyecto.
# Ejecutar desde ~/proyecto_aforo/

set -e

echo "=== [1/5] Instalando dependencias del sistema ==="
sudo apt install -y python3 python3-pip python3-venv python3-dev

echo "=== [2/5] Creando entorno virtual afov ==="
python3 -m venv afov

echo "=== [3/5] Activando venv ==="
source ~/proyecto_aforo/afov/bin/activate
pip install --upgrade pip

echo "=== [4/5] Instalando librerias ==="
mkdir -p ~/tmp

# Instalar torch CPU primero antes que ultralytics
# Si se instala ultralytics primero, jala torch con dependencias de CUDA/nvidia
# que no sirven en ARM y ocupan espacio innecesario
TMPDIR=~/tmp pip install --prefer-binary \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# lapx es el reemplazo de lap para ARM/Python 3.13
# es dependencia del tracker de ultralytics, instalar antes que ultralytics
TMPDIR=~/tmp pip install --prefer-binary lapx

# ncnn es el backend para correr el modelo en formato NCNN
TMPDIR=~/tmp pip install --prefer-binary ncnn

# resto de dependencias
TMPDIR=~/tmp pip install --prefer-binary \
    opencv-python \
    pyserial \
    RPi.GPIO \
    numpy \
    flask \
    ultralytics

echo "=== [5/5] Listo ==="
echo "Venv creado en ~/proyecto_aforo/afov"
echo "Para activarlo manualmente: source ~/proyecto_aforo/afov/bin/activate"
