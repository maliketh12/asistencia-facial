"use strict";

const $ = (id) => document.getElementById(id);
const video = $("video");
const overlay = $("overlay");
const ctx = overlay.getContext("2d");
const marco = $("marco");

const SCAN_INTERVAL_MS = 1500; // cada cuánto se envía un fotograma al servidor
const SEND_WIDTH = 640;        // ancho al que se reduce el fotograma antes de enviarlo

let stream = null;
let scanTimer = null;
let busy = false;
let justMarked = new Set();

/* ---------- Utilidades ---------- */
function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " error" : "");
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 3500);
}

function setStatus(message, kind = "") {
  const el = $("estado");
  el.textContent = message;
  el.className = "estado " + kind;
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = "Ocurrió un error en el servidor.";
    try { detail = (await res.json()).detail || detail; } catch (_) { /* sin cuerpo JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

function postJSON(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/* Captura el fotograma actual del video como imagen JPEG (dataURL). */
function captureFrame() {
  const w = SEND_WIDTH;
  const h = Math.round((video.videoHeight / video.videoWidth) * w);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  canvas.getContext("2d").drawImage(video, 0, 0, w, h);
  return canvas.toDataURL("image/jpeg", 0.85);
}

/* ---------- Cámara ---------- */
async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: false,
    });
  } catch (err) {
    setStatus("No se pudo acceder a la cámara. Revisa los permisos del navegador.", "alerta");
    return;
  }
  video.srcObject = stream;
  await new Promise((resolve) => (video.onloadedmetadata = resolve));
  marco.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
  marco.classList.add("activa");
  $("btnCamara").textContent = "Apagar cámara";
  $("btnEscaneo").disabled = false;
  $("btnCapturar").disabled = false;
  setStatus("Cámara lista. Pulsa “Iniciar pase de lista”.");
}

function stopCamera() {
  stopScanning();
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null;
  video.srcObject = null;
  marco.classList.remove("activa");
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  $("btnCamara").textContent = "Encender cámara";
  $("btnEscaneo").disabled = true;
  $("btnCapturar").disabled = true;
  setStatus("Enciende la cámara para empezar.");
}

/* ---------- Escaneo automático ---------- */
function startScanning() {
  $("btnEscaneo").textContent = "Detener pase de lista";
  $("btnEscaneo").classList.add("escaneando");
  setStatus("Buscando rostros…");
  scanOnce();
  scanTimer = setInterval(scanOnce, SCAN_INTERVAL_MS);
}

function stopScanning() {
  clearInterval(scanTimer);
  scanTimer = null;
  $("btnEscaneo").textContent = "Iniciar pase de lista";
  $("btnEscaneo").classList.remove("escaneando");
  ctx.clearRect(0, 0, overlay.width, overlay.height);
}

async function scanOnce() {
  if (busy || !stream) return;
  busy = true;
  try {
    const data = await postJSON("/api/recognize", { image: captureFrame() });
    drawFaces(data);
    describe(data.faces);
    if (data.faces.some((f) => f.new)) {
      data.faces.filter((f) => f.new).forEach((f) => justMarked.add(f.name));
      await refreshToday();
    }
  } catch (err) {
    setStatus(err.message, "alerta");
  } finally {
    busy = false;
  }
}

function describe(faces) {
  if (faces.length === 0) return setStatus("Buscando rostros…");
  const fresh = faces.filter((f) => f.new);
  if (fresh.length) {
    return setStatus(`Asistencia registrada: ${fresh.map((f) => f.name).join(", ")}`, "ok");
  }
  const known = faces.filter((f) => f.name);
  const unknown = faces.length - known.length;
  const parts = [];
  if (known.length) parts.push(`${known.map((f) => f.name).join(", ")} ya estaba registrado hoy`);
  if (unknown) parts.push(`${unknown} rostro(s) sin reconocer`);
  setStatus(parts.join(" · "), unknown ? "alerta" : "ok");
}

/* Dibuja los recuadros sobre el video (invertidos, porque el video se muestra en espejo). */
function drawFaces({ width, height, faces }) {
  overlay.width = width;
  overlay.height = height;
  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 3;
  ctx.font = "600 18px 'Segoe UI', system-ui, sans-serif";

  faces.forEach((f) => {
    const x = width - (f.x + f.w);
    const color = f.name ? "#1f9d6b" : "#e8590c";
    ctx.strokeStyle = color;
    ctx.strokeRect(x, f.y, f.w, f.h);

    const label = f.name ? `${f.name} · ${f.similarity}%` : "Sin reconocer";
    const textWidth = ctx.measureText(label).width + 14;
    const labelY = f.y > 28 ? f.y - 28 : f.y + f.h;
    ctx.fillStyle = color;
    ctx.fillRect(x, labelY, textWidth, 28);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, x + 7, labelY + 20);
  });
}

/* ---------- Lista de hoy ---------- */
async function refreshToday() {
  const data = await api("/api/attendance/today");
  const people = await api("/api/people");
  const contacts = Object.fromEntries(people.map((p) => [p.nombre, p]));

  $("fecha").textContent = new Date(data.fecha + "T00:00:00").toLocaleDateString("es-MX", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  $("contador").textContent = `${data.presentes.length} de ${data.total} presentes`;

  const list = $("listaPersonas");
  list.replaceChildren();
  $("listaVacia").hidden = data.total > 0;

  const rows = [
    ...data.presentes.sort((a, b) => a.hora.localeCompare(b.hora)).map((p) => ({ ...p, presente: true })),
    ...data.ausentes.map((p) => ({ ...p, presente: false })),
  ];

  rows.forEach((p) => {
    const li = document.createElement("li");
    li.className = "persona " + (p.presente ? "presente" : "pendiente");
    if (justMarked.has(p.nombre)) li.classList.add("recien");

    const marca = document.createElement("span");
    marca.className = "marca";
    marca.textContent = "✓";

    const nombre = document.createElement("span");
    nombre.className = "nombre";
    nombre.textContent = p.nombre;

    const detalle = document.createElement("span");
    detalle.className = "detalle";
    const samples = contacts[p.nombre] ? contacts[p.nombre].muestras : 0;
    detalle.textContent = p.presente ? p.hora : `Pendiente · ${samples} foto(s)`;

    const quitar = document.createElement("button");
    quitar.className = "quitar";
    quitar.textContent = "Quitar";
    quitar.setAttribute("aria-label", `Quitar a ${p.nombre}`);
    quitar.addEventListener("click", () => removePerson(p.nombre));

    li.append(marca, nombre, detalle, quitar);
    list.appendChild(li);
  });
  justMarked = new Set();
}

async function removePerson(name) {
  if (!confirm(`¿Quitar a ${name} del sistema? Se borrarán sus fotos registradas.`)) return;
  try {
    await api(`/api/people/${encodeURIComponent(name)}`, { method: "DELETE" });
    toast(`${name} fue eliminado.`);
    await refreshToday();
  } catch (err) {
    toast(err.message, true);
  }
}

/* ---------- Registro de personas ---------- */
async function registerPhoto(imageDataUrl) {
  const name = $("inNombre").value.trim();
  if (!name) {
    toast("Escribe el nombre de la persona antes de guardar la foto.", true);
    $("inNombre").focus();
    return;
  }
  try {
    const res = await postJSON("/api/register", {
      name,
      contact: $("inContacto").value.trim(),
      image: imageDataUrl,
    });
    toast(`Foto ${res.muestras} guardada para ${res.nombre}.`);
    await refreshToday();
  } catch (err) {
    toast(err.message, true);
  }
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/* ---------- Eventos ---------- */
$("btnCamara").addEventListener("click", () => (stream ? stopCamera() : startCamera()));
$("btnEscaneo").addEventListener("click", () => (scanTimer ? stopScanning() : startScanning()));

$("btnCapturar").addEventListener("click", async () => {
  $("btnCapturar").disabled = true;
  await registerPhoto(captureFrame());
  $("btnCapturar").disabled = !stream;
});

$("inArchivo").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  ev.target.value = "";
  if (file) await registerPhoto(await readFileAsDataURL(file));
});

$("btnCerrar").addEventListener("click", async () => {
  try {
    const data = await api("/api/close-session", { method: "POST" });
    const box = $("avisos");
    const ul = $("avisosLista");
    ul.replaceChildren();
    if (data.notificaciones.length === 0) {
      const li = document.createElement("li");
      li.textContent = "Todos asistieron. No hay avisos que enviar.";
      ul.appendChild(li);
    }
    data.notificaciones.forEach((n) => {
      const li = document.createElement("li");
      li.textContent = `Aviso a ${n.destino}: ${n.mensaje}`;
      ul.appendChild(li);
    });
    box.hidden = false;
    toast("Lista cerrada.");
  } catch (err) {
    toast(err.message, true);
  }
});

$("btnReiniciar").addEventListener("click", async () => {
  if (!confirm("¿Borrar las asistencias de hoy? Las personas registradas se conservan.")) return;
  await api("/api/attendance/today", { method: "DELETE" });
  $("avisos").hidden = true;
  await refreshToday();
  toast("Asistencias de hoy reiniciadas.");
});

refreshToday().catch((err) => toast(err.message, true));
