@echo off
REM Crea el entorno virtual, instala dependencias y arranca el servidor (Windows).
cd /d "%~dp0"

if not exist venv (
  echo ^>^> Creando entorno virtual...
  python -m venv venv
)

call venv\Scripts\activate.bat
echo ^>^> Instalando dependencias...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ^>^> Servidor listo en http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
