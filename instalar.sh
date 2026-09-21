#!/bin/sh
# ============================================================
#  Instala lo necesario para usar ConsolaOBS en Linux/macOS.
#  Uso:  bash instalar.sh   (no hace falta chmod +x)
#
#  Después se usa con:  python3 main.py
#  (opcional: generar binario con PyInstaller, ver README)
# ============================================================

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "======================================================"
    echo " NO SE ENCONTRO PYTHON."
    echo " Instalá Python 3.9 o más nuevo con tu gestor de paquetes"
    echo " (ej: sudo apt install python3 python3-pip python3-tk)"
    echo " y volvé a correr este archivo."
    echo "======================================================"
    exit 1
fi

echo "Python encontrado:"
python3 --version
echo ""

if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "======================================================"
    echo " AVISO: a este Python le falta tkinter (la interfaz)."
    echo " En Debian/Ubuntu:  sudo apt install python3-tk"
    echo " Sigo igual con el resto, pero el programa no va a abrir"
    echo " hasta instalarlo."
    echo "======================================================"
fi

if [ ! -f "requirements.txt" ]; then
    echo "======================================================"
    echo " No se encontró requirements.txt junto a este archivo."
    echo " Asegurate de haber descomprimido TODO el .zip en una"
    echo " carpeta."
    echo "======================================================"
    exit 1
fi

echo "Instalando dependencias (puede tardar unos minutos)..."
if ! python3 -m pip install -r "requirements.txt"; then
    echo "======================================================"
    echo " ALGO FALLO instalando las dependencias."
    echo " Si pip se queja del entorno (externally-managed), probá con:"
    echo "   python3 -m venv .venv && . .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    echo "======================================================"
    exit 1
fi

echo ""
echo "======================================================"
echo " Listo. Abrí el programa con:  python3 main.py"
echo "======================================================"
