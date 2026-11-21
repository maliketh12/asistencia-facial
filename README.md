# Pase de lista con reconocimiento facial

Proyecto final de visión por computadora: **Sistema de asistencia automatizada con reconocimiento facial**.

La cámara reconoce el rostro de cada persona en tiempo real, registra su asistencia (una vez por día) y, al cerrar la lista, "avisa" a los padres o supervisores de quienes no asistieron.

Está inspirado en la estructura del repositorio [computerV (MoodMeter)](https://github.com/mendiolaleonel2002-debug/computerV): backend con **FastAPI + DeepFace + OpenCV**, frontend web con la cámara del navegador y un script de arranque automático.

---

## Qué hace

| Funcionalidad | Cómo funciona |
|---|---|
| **Registro de personas** | Se escribe el nombre (y un contacto opcional) y se guardan fotos desde la cámara o desde un archivo. De cada foto se guarda un *embedding* (vector numérico del rostro). |
| **Reconocimiento en tiempo real** | Cada 1.5 s se envía un fotograma al servidor, que detecta los rostros y los compara con los registrados. Los recuadros se dibujan sobre el video: verde si se reconoce, naranja si no. |
| **Asistencia automática** | La primera vez que se reconoce a alguien en el día se guarda fecha, hora y nombre en `data/asistencia.csv`. No se duplica. |
| **Lista del día** | Panel tipo hoja de asistencia: cada persona se marca con ✓ y su hora al ser reconocida. |
| **Aviso a ausentes (simulado)** | El botón *Cerrar lista y avisar ausentes* imprime en consola y guarda en `data/notificaciones.log` un aviso por cada ausente, dirigido a su contacto. |
| **Exportar** | Botón *Descargar CSV* con todo el historial de asistencia. |

---

## Cómo funciona la visión por computadora

```
[ Cámara del navegador ]
          │  fotograma JPEG cada 1.5 s
          ▼
[ Detector de rostros (OpenCV) ]  ──> localiza y alinea cada rostro
          │
          ▼
[ Red neuronal Facenet (DeepFace) ] ──> convierte el rostro en un vector de 128 números (embedding)
          │
          ▼
[ Distancia coseno contra los rostros registrados ]
          │   distancia ≤ 0.40  → misma persona
          ▼
[ Registro en asistencia.csv ] ──> una vez por persona y por día
```

La **distancia coseno** mide qué tan parecidos son dos vectores:

$$d(a, b) = 1 - \frac{a \cdot b}{\lVert a \rVert \, \lVert b \rVert}$$

Si `d` es menor o igual a **0.40** (umbral recomendado para Facenet), se considera que es la misma persona. El porcentaje que se muestra sobre el recuadro es `(1 - d) × 100`.

---

## Requisitos

- **Python 3.9 a 3.12** (TensorFlow todavía no funciona con versiones más nuevas).
- Una **cámara web** (o fotos de las personas, que se pueden subir desde un archivo).
- Conexión a internet **solo la primera vez** (para instalar dependencias y descargar los pesos del modelo, unos ~90 MB).

---

## Instalación y ejecución

### Opción A: script automático

**macOS / Linux**

```bash
cd asistencia-facial
./start.sh
```

**Windows**

```bat
cd asistencia-facial
start.bat
```

El script crea el entorno virtual `venv`, instala `requirements.txt` y arranca el servidor.

### Opción B: paso a paso

```bash
cd asistencia-facial

# 1. Crear el entorno virtual
python3 -m venv venv            # en Windows: python -m venv venv

# 2. Activarlo
source venv/bin/activate        # en Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

# 4. Arrancar el servidor
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Abrir la aplicación

Con el servidor corriendo, abre **http://127.0.0.1:8000** en el navegador (Chrome, Edge o Firefox) y **permite el acceso a la cámara**.

> La primera vez, DeepFace descarga los pesos del modelo Facenet. La terminal mostrará el progreso y el primer escaneo puede tardar unos segundos más. Después es instantáneo.

---

## Cómo probarlo (guía para quien califique)

1. Pulsa **Encender cámara** y acepta el permiso del navegador.
2. Abre **Registrar una persona**, escribe un nombre y un contacto (por ejemplo `mamá de Ana: 222 123 4567`) y pulsa **Guardar foto desde la cámara**. Repite 3 o 4 veces con pequeños cambios de ángulo.
   - Para tener personas ausentes, registra al menos a dos personas distintas (la segunda puede ser con una foto subida desde un archivo).
3. Pulsa **Iniciar pase de lista**. Al reconocerte aparecerá un recuadro verde con tu nombre y la lista mostrará ✓ con la hora.
4. Pulsa **Cerrar lista y avisar ausentes**. Verás los avisos simulados en pantalla, y en la terminal del servidor el texto `[NOTIFICACIÓN SIMULADA] ...`.
5. Pulsa **Descargar CSV** para obtener el registro de asistencia.
6. **Reiniciar hoy** borra las asistencias del día para repetir la demostración (las personas registradas se conservan).

---

## Estructura del repositorio

```
asistencia-facial/
├── app/
│   ├── main.py            # API FastAPI: detección, reconocimiento, asistencia y avisos
│   └── static/
│       ├── index.html     # Interfaz web
│       ├── style.css      # Estilos
│       └── app.js         # Cámara, escaneo automático y lista de asistencia
├── data/                  # Se llena al usar la app (personas.json, asistencia.csv, notificaciones.log)
├── requirements.txt       # Dependencias de Python
├── start.sh               # Arranque automático (macOS / Linux)
├── start.bat              # Arranque automático (Windows)
└── README.md
```

Los datos se guardan en archivos locales dentro de `data/`: no se necesita base de datos.

---

## Ajustes

| Qué | Dónde | Notas |
|---|---|---|
| Umbral de reconocimiento | `THRESHOLD` en `app/main.py` | Más bajo = más estricto (menos falsos positivos, más "sin reconocer"). |
| Modelo de rostros | `MODEL_NAME` en `app/main.py` | Si lo cambias, borra `data/personas.json` y vuelve a registrar a las personas. |
| Detector de rostros | Variable de entorno `FACE_DETECTOR` | Por defecto `opencv` (rápido, pide rostro de frente). Prueba `ssd` para más precisión. |
| Frecuencia de escaneo | `SCAN_INTERVAL_MS` en `app/static/app.js` | |

---

## Solución de problemas

- **"No se pudo acceder a la cámara"**: revisa los permisos del navegador y que no la use otra aplicación. La cámara solo funciona en `127.0.0.1` / `localhost`.
- **"No se detectó ningún rostro" al registrar**: mejora la iluminación y mira de frente; debe aparecer una sola persona en la imagen.
- **Falla `pip install tensorflow`**: verifica con `python --version` que tengas Python entre 3.9 y 3.12.
- **Reconoce a la persona equivocada o no la reconoce**: registra más fotos (3 o 4 por persona) y ajusta `THRESHOLD`.

---

## Privacidad

Los rostros se guardan solo como vectores numéricos en `data/personas.json`, en tu propia computadora, y nada se envía a servicios externos. Las notificaciones son simuladas. En un uso real se necesita el consentimiento de las personas registradas.

## Tecnologías

- **FastAPI** + **Uvicorn**: servidor y API.
- **DeepFace** (modelo **Facenet**) + **TensorFlow**: embeddings faciales.
- **OpenCV**: decodificación de imágenes y detección de rostros.
- **HTML5 / CSS3 / JavaScript**: interfaz y acceso a la cámara (sin librerías externas).
