#!/usr/bin/env bash
# Crea el entorno virtual, instala dependencias y arranca el servidor.
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo ">> Creando entorno virtual..."
  python3 -m venv venv
fi

source venv/bin/activate
echo ">> Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

echo ">> Servidor listo en http://127.0.0.1:8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000
