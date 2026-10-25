// Entrevista Vertical · interfaz. Habla con app.py por /api.
const $ = (s) => document.querySelector(s);
const COLORES = ["#d9480f", "#1971c2", "#2b8a3e", "#9c36b5", "#e67700", "#0c8599"];
let P = null;          // proyecto actual (respuesta de /api/p/<id>)
let sondeo = null;

const api = async (url, opts = {}) => {
  const r = await fetch(url, opts);
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || "Error");
  return d;
};
const enviar = (url, datos) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const segs = (s) => { const [m, x] = String(s).split(":").map(Number); return x === undefined ? m : m * 60 + x; };
const aviso = (txt) => { const a = $("#aviso"); a.textContent = txt || ""; a.hidden = !txt; };

function vista(nombre) {
  for (const s of document.querySelectorAll("main > section")) s.hidden = s.id !== "v-" + nombre;
  const orden = ["subir", "personas", "analizar", "revisar", "render"];
  const paso = nombre === "progreso" ? (P?.estado?.fase === "renderizar" ? "render" : "analizar") : nombre;
  document.querySelectorAll("#pasos li").forEach((li) => {
    const i = orden.indexOf(li.dataset.paso), j = orden.indexOf(paso);
    li.className = i === j ? "activo" : i < j ? "hecho" : "";
  });
  if (P) history.replaceState(null, "", "#" + P.id);
}

// ---------- 1 · subir ----------
async function cargarRecientes() {
  const lista = await api("/api/proyectos");
  $("#recientes").innerHTML = lista.length ? "<h3>Proyectos anteriores</h3>" +
    lista.map((p) => `<a href="#${p.id}">${p.nombre || p.id} <small>· ${p.fase || ""}</small></a>`).join("") : "";
}

function subir(file) {
  $("#subiendo").hidden = false;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/subir?nombre=" + encodeURIComponent(file.name));
  xhr.upload.onprogress = (e) => {
    const f = e.loaded / e.total;
    $("#barra-subida").style.width = (f * 100).toFixed(1) + "%";
    $("#txt-subida").textContent = `Copiando el vídeo… ${(f * 100).toFixed(0)} %`;
  };
  xhr.onload = () => {
    const d = JSON.parse(xhr.responseText);
    $("#subiendo").hidden = true;
    if (xhr.status !== 200) return aviso(d.error);
    P = d;
    mostrar();
  };
  xhr.send(file);
}
$("#archivo").onchange = (e) => e.target.files[0] && subir(e.target.files[0]);
const zona = $("#zona");
zona.ondragover = (e) => { e.preventDefault(); zona.classList.add("encima"); };
zona.ondragleave = () => zona.classList.remove("encima");
zona.ondrop = (e) => { e.preventDefault(); zona.classList.remove("encima"); e.dataTransfer.files[0] && subir(e.dataTransfer.files[0]); };

// ---------- 2 · personas ----------
function pintarPersonas() {
  const ps = P.config.personas;
  $("#puntos").innerHTML = ps.map((p, i) =>
    `<div class="punto" style="left:${p.x * 100}%;top:${p.y * 100}%;background:${COLORES[i % 6]}">${i + 1}</div>`).join("");
  $("#lista-personas").innerHTML = ps.map((p, i) => `
    <div class="persona"><span class="chip" style="background:${COLORES[i % 6]}">${i + 1}</span>
      <input data-i="${i}" class="nombre-persona" value="${p.nombre || ""}" placeholder="Nombre (opcional)">
      <button class="quitar" data-i="${i}">Quitar</button></div>`).join("") ||
    `<p class="nota">Todavía no has marcado a nadie.</p>`;
  document.querySelectorAll(".nombre-persona").forEach((el) => el.onchange = () => { ps[+el.dataset.i].nombre = el.value; guardarConfig(); });
  document.querySelectorAll(".persona .quitar").forEach((el) => el.onclick = () => { ps.splice(+el.dataset.i, 1); pintarPersonas(); guardarConfig(); });
}
$(".marco").onclick = (e) => {
  const r = $("#foto").getBoundingClientRect();
  if (P.config.personas.length >= 6) return aviso("Como máximo 6 personas.");
  P.config.personas.push({ x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height, nombre: "" });
  pintarPersonas();
  guardarConfig();
};
async function guardarConfig(extra = {}) {
  const c = P.config;
  document.querySelectorAll(".nombre-persona").forEach((el) => { if (c.personas[+el.dataset.i]) c.personas[+el.dataset.i].nombre = el.value; });
  P = await enviar(`/api/p/${P.id}/config`, {
    personas: c.personas, nombre: $("#nombre").value, partes: +$("#partes").value || 1, idioma: $("#idioma").value,
    modelo: $("#modelo").value, vocabulario: $("#vocabulario").value, ...extra,
  });
}
$("#btn-analizar").onclick = async () => {
  try {
    aviso("");
    await guardarConfig();
    P = await api(`/api/p/${P.id}/analizar`, { method: "POST" });
    mostrar();
  } catch (e) { aviso(e.message); }
};

// ---------- 3 · progreso ----------
function progreso() {
  vista("progreso");
  const e = P.estado || {};
  $("#prog-titulo").textContent = e.fase === "error" ? "Algo ha fallado" : e.fase === "renderizar" ? "Renderizando…" : "Analizando…";
  $("#barra").style.width = ((e.progreso || 0) * 100).toFixed(0) + "%";
  $("#prog-paso").textContent = e.paso || "";
  $("#prog-log").innerHTML = (e.log || []).slice(0, -1).map((x) => `<li>${x}</li>`).join("");
  $("#prog-error").hidden = !e.error;
  $("#prog-error").textContent = e.error || "";
  $("#btn-reintentar").hidden = e.fase !== "error";
  $("#btn-reintentar").onclick = () => (P.plan ? pintarRevisar() : (P.estado.fase = "nuevo", mostrar()));
  clearTimeout(sondeo);
  if (e.fase === "analizar" || e.fase === "renderizar") sondeo = setTimeout(async () => { P = await api(`/api/p/${P.id}`); mostrar(); }, 2000);
}

// ---------- 4 · revisar ----------
function nombrePersona(i) { const p = P.config.personas[i]; return `${i + 1}${p && p.nombre ? " · " + p.nombre : ""}`; }

function pintarRevisar() {
  vista("revisar");
  const plan = P.plan, n = P.config.personas.length;
  $("#voces").innerHTML = plan.voces.map((v, i) => `
    <div class="voz"><audio controls preload="none" src="/api/p/${P.id}/muestra/${i}"></audio>
      <span>es la persona</span>
      <select data-v="${i}" class="voz-persona">${Array.from({ length: n }, (_, j) =>
        `<option value="${j}" ${j === v.persona ? "selected" : ""}>${nombrePersona(j)}</option>`).join("")}</select></div>`).join("");
  document.querySelectorAll(".voz-persona").forEach((el) => el.onchange = async () => {
    const voces = [...document.querySelectorAll(".voz-persona")].map((s) => +s.value);
    P = await enviar(`/api/p/${P.id}/plan`, { voces });
  });
  const lim = [0, ...plan.cortes, plan.duracion];
  $("#cortes").innerHTML = plan.cortes.length ? plan.cortes.map((t, i) => {
    const [antes, despues] = plan.contexto?.[i] || ["", ""];
    return `<div class="corte"><span>Corte ${i + 1} en</span>
      <input class="t-corte" data-i="${i}" value="${mmss(t)}" size="6">
      <small>Parte ${i + 1}: ${mmss(lim[i + 1] - lim[i])} · Parte ${i + 2}: ${mmss(lim[i + 2] - lim[i + 1])}</small>
      <button class="quitar" data-i="${i}">Quitar</button>
      <div class="contexto">…${antes} <b>✂</b> ${despues}…</div></div>`;
  }).join("") : `<p class="nota">Sin cortes: saldrá un solo vídeo de ${mmss(plan.duracion)}.</p>`;
  const guardarCortes = async (cortes) => { P = await enviar(`/api/p/${P.id}/plan`, { cortes }); pintarRevisar(); };
  document.querySelectorAll(".t-corte").forEach((el) => el.onchange = () => {
    const c = [...plan.cortes]; c[+el.dataset.i] = segs(el.value); guardarCortes(c);
  });
  document.querySelectorAll(".corte .quitar").forEach((el) => el.onclick = () => guardarCortes(plan.cortes.filter((_, i) => i !== +el.dataset.i)));
  $("#btn-mas-corte").onclick = () => {
    const t = prompt("¿En qué minuto? (mm:ss)");
    if (t) guardarCortes([...plan.cortes, segs(t)]);
  };
  const c = P.config;
  $("#quemados").checked = !!c.subtitulos_quemados;
  $("#correcciones").value = Object.entries(c.correcciones || {}).map(([a, b]) => `${a} = ${b}`).join("\n");
  $("#musica-donde").value = c.musica_donde || "auto";
}
$("#musica").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  P = await api(`/api/p/${P.id}/musica?nombre=${encodeURIComponent(f.name)}`, { method: "POST", body: f });
};
$("#btn-render").onclick = async () => {
  try {
    aviso("");
    const correcciones = {};
    for (const l of $("#correcciones").value.split("\n")) {
      const [a, b] = l.split("=");
      if (a && b && a.trim()) correcciones[a.trim()] = b.trim();
    }
    P = await enviar(`/api/p/${P.id}/config`, { subtitulos_quemados: $("#quemados").checked, correcciones, musica_donde: $("#musica-donde").value });
    P = await api(`/api/p/${P.id}/renderizar`, { method: "POST" });
    mostrar();
  } catch (e) { aviso(e.message); }
};

// ---------- 5 · resultado ----------
function pintarSalidas() {
  vista("render");
  $("#carpeta").textContent = `proyectos/${P.id}/salida`;
  $("#salidas").innerHTML = (P.salidas || []).map((s) => {
    const nombre = s.video.split("/").pop();
    return `<div class="salida"><video controls preload="metadata" src="/archivos/${P.id}/${encodeURI(s.video)}"></video>
      <div><b>${nombre}</b><br><small>${mmss(s.inicio)} – ${mmss(s.fin)} · ${s.lufs} LUFS</small><br>
      <a href="/archivos/${P.id}/${encodeURI(s.video)}">Descargar vídeo</a> · <a href="/archivos/${P.id}/${encodeURI(s.srt)}">Subtítulos .srt</a></div></div>`;
  }).join("");
}
$("#btn-otra").onclick = () => pintarRevisar();
$("#btn-nuevo").onclick = () => { P = null; history.replaceState(null, "", "/"); mostrar(); };

// ---------- enrutado ----------
function mostrar() {
  if (!P) { vista("subir"); cargarRecientes(); return; }
  const fase = P.estado?.fase;
  if (fase === "analizar" || fase === "renderizar" || fase === "error") return progreso();
  if (fase === "terminado") return pintarSalidas();
  if (fase === "listo_para_revisar" && P.plan) return pintarRevisar();
  vista("personas");
  $("#foto").src = `/archivos/${P.id}/fotograma.jpg`;
  $("#nombre").value = P.config.nombre || "";
  $("#partes").value = P.config.partes || 1;
  $("#idioma").value = P.config.idioma || "es";
  $("#modelo").value = P.config.modelo || "turbo";
  $("#vocabulario").value = P.config.vocabulario || "";
  pintarPersonas();
}

async function iniciar() {
  const s = await api("/api/salud");
  if (s.faltan.length) aviso(`Falta instalar ${s.faltan.join(", ")}. En Mac: brew install ffmpeg`);
  const id = location.hash.slice(1);
  if (id) { try { P = await api(`/api/p/${id}`); } catch { P = null; } }
  mostrar();
}
window.onhashchange = async () => { const id = location.hash.slice(1); if (id && id !== P?.id) { P = await api(`/api/p/${id}`); mostrar(); } };
iniciar();
