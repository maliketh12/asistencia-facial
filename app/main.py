"""
Sistema de asistencia automatizada con reconocimiento facial.

Flujo:
  1. Se registran personas (nombre + fotos de su rostro). De cada foto se guarda
     un "embedding" (vector numérico) generado por una red neuronal (Facenet).
  2. La cámara envía fotogramas al servidor. Se detectan los rostros (OpenCV),
     se calculan sus embeddings y se comparan contra los registrados.
  3. Si la distancia es menor al umbral, se reconoce a la persona y se registra
     su asistencia (una vez por día) en data/asistencia.csv.
  4. Al cerrar el pase de lista, se "notifica" (simulado) a los ausentes.
"""
import base64
import csv
import json
import os
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from deepface import DeepFace
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR.parent / "data"
PEOPLE_FILE = DATA_DIR / "personas.json"
ATTENDANCE_FILE = DATA_DIR / "asistencia.csv"
NOTIFY_LOG = DATA_DIR / "notificaciones.log"

MODEL_NAME = "Facenet"  # red neuronal que genera los embeddings (128 dimensiones)
DETECTOR = os.getenv("FACE_DETECTOR", "opencv")  # detector de rostros
THRESHOLD = 0.40  # distancia coseno máxima para considerar "misma persona" (Facenet)

infer_lock = threading.Lock()  # el modelo no se usa en paralelo
data_lock = threading.RLock()  # protege personas.json y asistencia.csv

DATA_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------
# Persistencia (JSON para personas, CSV para asistencia)
# --------------------------------------------------------------------------


def load_people() -> dict:
    if not PEOPLE_FILE.exists():
        return {}
    return json.loads(PEOPLE_FILE.read_text(encoding="utf-8"))


def save_people(people: dict) -> None:
    PEOPLE_FILE.write_text(json.dumps(people, ensure_ascii=False), encoding="utf-8")


def ensure_attendance_file() -> None:
    if not ATTENDANCE_FILE.exists():
        with open(ATTENDANCE_FILE, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(["fecha", "hora", "nombre"])


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_today() -> list[dict]:
    """Registros de asistencia de hoy."""
    ensure_attendance_file()
    with data_lock, open(ATTENDANCE_FILE, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r["fecha"] == today_str()]


def mark_attendance(name: str) -> bool:
    """Registra la asistencia de hoy. Devuelve True si es la primera vez hoy."""
    with data_lock:
        if any(r["nombre"] == name for r in read_today()):
            return False
        now = datetime.now()
        with open(ATTENDANCE_FILE, "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), name])
        return True


people_db = load_people()
ensure_attendance_file()

# --------------------------------------------------------------------------
# Visión por computadora
# --------------------------------------------------------------------------


def decode_image(data_url: str) -> np.ndarray:
    """Convierte una imagen base64 (dataURL) a un arreglo BGR de OpenCV."""
    try:
        encoded = data_url.split(",", 1)[1] if "," in data_url else data_url
        buffer = np.frombuffer(base64.b64decode(encoded), dtype=np.uint8)
        img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        raise HTTPException(status_code=400, detail="La imagen no es válida.")
    return img


def extract_faces(img: np.ndarray) -> list[dict]:
    """Detecta rostros y calcula el embedding de cada uno."""
    with infer_lock:
        try:
            return DeepFace.represent(
                img_path=img,
                model_name=MODEL_NAME,
                detector_backend=DETECTOR,
                enforce_detection=True,
                align=True,
            )
        except ValueError:  # DeepFace lanza ValueError si no encuentra rostros
            return []


def cosine_distance(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    return float(1.0 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def best_match(embedding) -> tuple[str | None, float]:
    """Persona registrada más parecida al embedding (nombre, distancia)."""
    best_name, best_dist = None, 2.0
    with data_lock:
        snapshot = {n: p["embeddings"] for n, p in people_db.items()}
    for name, embeddings in snapshot.items():
        for known in embeddings:
            d = cosine_distance(embedding, known)
            if d < best_dist:
                best_name, best_dist = name, d
    return best_name, best_dist


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
app = FastAPI(title="Asistencia con Reconocimiento Facial")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ImageBody(BaseModel):
    image: str


class RegisterBody(BaseModel):
    name: str
    contact: str = ""
    image: str


@app.on_event("startup")
def warm_up_model() -> None:
    """Carga el modelo en segundo plano para que el primer escaneo no tarde tanto."""

    def _warm():
        try:
            blank = np.zeros((160, 160, 3), dtype=np.uint8)
            with infer_lock:
                DeepFace.represent(
                    img_path=blank,
                    model_name=MODEL_NAME,
                    detector_backend=DETECTOR,
                    enforce_detection=False,
                )
            print(">> Modelo de reconocimiento facial listo.")
        except Exception as exc:  # no es crítico
            print(f">> No se pudo precargar el modelo: {exc}")

    threading.Thread(target=_warm, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/people")
def list_people():
    with data_lock:
        return [
            {"nombre": n, "contacto": p.get("contact", ""), "muestras": len(p["embeddings"])}
            for n, p in sorted(people_db.items())
        ]


@app.post("/api/register")
def register_person(body: RegisterBody):
    name = " ".join(body.name.split())[:60]
    if not name:
        raise HTTPException(status_code=400, detail="Escribe el nombre de la persona.")

    faces = extract_faces(decode_image(body.image))
    if len(faces) == 0:
        raise HTTPException(status_code=400, detail="No se detectó ningún rostro. Mejora la luz y mira a la cámara.")
    if len(faces) > 1:
        raise HTTPException(status_code=400, detail=f"Se detectaron {len(faces)} rostros. Debe aparecer solo uno.")

    with data_lock:
        person = people_db.setdefault(
            name,
            {"contact": "", "embeddings": [], "created": datetime.now().isoformat(timespec="seconds")},
        )
        if body.contact.strip():
            person["contact"] = body.contact.strip()
        person["embeddings"].append(faces[0]["embedding"])
        save_people(people_db)
        samples = len(person["embeddings"])

    return {"ok": True, "nombre": name, "muestras": samples}


@app.delete("/api/people/{name}")
def delete_person(name: str):
    with data_lock:
        if name not in people_db:
            raise HTTPException(status_code=404, detail="Persona no encontrada.")
        del people_db[name]
        save_people(people_db)
    return {"ok": True}


@app.post("/api/recognize")
def recognize(body: ImageBody):
    img = decode_image(body.image)
    height, width = img.shape[:2]
    results = []

    for face in extract_faces(img):
        area = face["facial_area"]
        entry = {
            "x": int(area["x"]),
            "y": int(area["y"]),
            "w": int(area["w"]),
            "h": int(area["h"]),
            "name": None,
            "similarity": 0.0,
            "new": False,
        }
        name, dist = best_match(face["embedding"])
        if name is not None and dist <= THRESHOLD:
            entry["name"] = name
            entry["similarity"] = round(max(0.0, 1.0 - dist) * 100, 1)
            entry["new"] = mark_attendance(name)  # True solo la primera vez del día
        results.append(entry)

    return {"width": width, "height": height, "faces": results}


@app.get("/api/attendance/today")
def attendance_today():
    present = read_today()
    present_names = {r["nombre"] for r in present}
    with data_lock:
        absent = [
            {"nombre": n, "contacto": p.get("contact", "")}
            for n, p in sorted(people_db.items())
            if n not in present_names
        ]
        total = len(people_db)
    return {
        "fecha": today_str(),
        "total": total,
        "presentes": [{"nombre": r["nombre"], "hora": r["hora"]} for r in present if r["nombre"] in people_db],
        "ausentes": absent,
    }


@app.delete("/api/attendance/today")
def reset_today():
    """Borra las asistencias de hoy (útil para repetir la demostración)."""
    ensure_attendance_file()
    with data_lock:
        with open(ATTENDANCE_FILE, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r["fecha"] != today_str()]
        with open(ATTENDANCE_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["fecha", "hora", "nombre"])
            writer.writerows([[r["fecha"], r["hora"], r["nombre"]] for r in rows])
    return {"ok": True}


@app.get("/api/attendance/export")
def export_attendance():
    ensure_attendance_file()
    return FileResponse(ATTENDANCE_FILE, media_type="text/csv", filename="asistencia.csv")


@app.post("/api/close-session")
def close_session():
    """Cierra el pase de lista y 'notifica' a los ausentes (simulado con print + log)."""
    data = attendance_today()
    notifications = []
    for person in data["ausentes"]:
        destino = person["contacto"] or "(sin contacto registrado)"
        message = f"{person['nombre']} no asistió el {data['fecha']}."
        line = f"[NOTIFICACIÓN SIMULADA] Enviando aviso a {destino}: {message}"
        print(line)
        with data_lock, open(NOTIFY_LOG, "a", encoding="utf-8") as log:
            log.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
        notifications.append({"nombre": person["nombre"], "destino": destino, "mensaje": message})
    return {"fecha": data["fecha"], "notificaciones": notifications}
