#!/bin/bash
# instalar_dependencias.sh
# Crea el venv afov e instala todas las dependencias del proyecto.
# Ejecutar desde ~/proyecto_aforo/

set -e

echo "=== [1/5] Instalando dependencias del sistema ==="
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    liblgpio-dev \
    swig
# liblgpio-dev -> libreria C de lgpio necesaria para compilar el modulo Python
# swig         -> generador de bindings C/Python, requerido por lgpio al compilar

echo "=== [2/5] Creando entorno virtual afov ==="
python3 -m venv afov

echo "=== [3/5] Activando venv ==="
source ~/proyecto_aforo/afov/bin/activate
pip install --upgrade pip

echo "=== [4/5] Instalando librerias ==="
mkdir -p ~/tmp

# torch CPU primero, antes que ultralytics.
# Si se instala ultralytics primero, jala torch con dependencias CUDA/nvidia
# que no sirven en ARM y ocupan espacio innecesario.
TMPDIR=~/tmp pip install --prefer-binary \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# lapx es el reemplazo de lap para ARM/Python 3.13.
# Es dependencia interna del tracker de ultralytics, instalar antes que el.
TMPDIR=~/tmp pip install --prefer-binary lapx

# ncnn es el backend para correr el modelo en formato NCNN en la Pi.
TMPDIR=~/tmp pip install --prefer-binary ncnn

# lgpio: pip no tiene wheel precompilado para Python 3.13 en ARM,
# por eso compila desde fuente. Necesita liblgpio-dev y swig (instalados arriba).
# NO usar --prefer-binary aqui porque el wheel de PyPI es la version vieja 0.0.0.2
# que no tiene gpiochip_open. Compilar desde fuente da la version 0.2.2.0 correcta.
TMPDIR=~/tmp pip install lgpio

# Resto de dependencias.
TMPDIR=~/tmp pip install --prefer-binary \
    opencv-python \
    pyserial \
    numpy \
    flask \
    ultralytics

echo "=== [5/5] Listo ==="
echo "Venv creado en ~/proyecto_aforo/afov"
echo "Para activarlo manualmente: source ~/proyecto_aforo/afov/bin/activate"

echo ""
echo "--- Verificacion de lgpio ---"
~/proyecto_aforo/afov/bin/python -c "
import lgpio
h = lgpio.gpiochip_open(0)
if h >= 0:
    print('  lgpio OK - gpiochip_open funciona, handle:', h)
    lgpio.gpiochip_close(h)
else:
    print('  lgpio ERROR - handle negativo:', h)
"
