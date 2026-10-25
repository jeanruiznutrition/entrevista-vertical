"""Entrevista Vertical · servidor local. Solo usa la biblioteca estándar de Python.

  python app.py            → abre http://127.0.0.1:8765
  python app.py --puerto 9000 --no-abrir
"""
import argparse
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from motor import pipeline
from motor.analisis import fotograma
from motor.comun import RAIZ, Proyecto, faltan_programas, probe, run

PROYECTOS = os.path.join(RAIZ, "proyectos")
WEB = os.path.join(RAIZ, "web")
TRABAJO = threading.Lock()          # una tarea pesada cada vez (el portátil lo agradece)
ID = re.compile(r"^[0-9a-f]{12}$")


def proyecto(pid):
    if not ID.match(pid or "") or not os.path.isdir(os.path.join(PROYECTOS, pid)):
        return None
    return Proyecto(os.path.join(PROYECTOS, pid))


def lanzar(pr, fn, fase):
    if not TRABAJO.acquire(blocking=False):
        return False
    pr.estado(fase, "En cola…", 0)

    def tarea():
        try:
            fn(pr)
        finally:
            TRABAJO.release()
    threading.Thread(target=tarea, daemon=True).start()
    return True


def resumen(pr, pid):
    return {"id": pid, "config": pr.leer("config.json", {}), "estado": pr.leer("estado.json", {}),
            "plan": pr.leer("plan.json"), "salidas": pr.leer("salidas.json")}


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------- respuestas ----------
    def json(self, datos, codigo=200):
        b = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def archivo(self, path):
        if not os.path.isfile(path):
            return self.json({"error": "no existe"}, 404)
        tam = os.path.getsize(path)
        tipo = mimetypes.guess_type(path)[0] or "application/octet-stream"
        rango = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        a, b = 0, tam - 1
        if rango:
            a = int(rango.group(1) or 0)
            b = int(rango.group(2)) if rango.group(2) else tam - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a}-{b}/{tam}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(b - a + 1))
        if "/salida/" in path:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(os.path.basename(path))}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(a)
            quedan = b - a + 1
            try:
                while quedan > 0:
                    trozo = f.read(min(1 << 20, quedan))
                    if not trozo:
                        break
                    self.wfile.write(trozo)
                    quedan -= len(trozo)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def cuerpo_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def guardar_cuerpo(self, dst):
        n = int(self.headers.get("Content-Length", 0))
        with open(dst, "wb") as f:
            while n > 0:
                trozo = self.rfile.read(min(1 << 20, n))
                if not trozo:
                    break
                f.write(trozo)
                n -= len(trozo)

    # ---------- rutas ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        partes = [urllib.parse.unquote(x) for x in u.path.strip("/").split("/") if x]
        if not partes:
            return self.archivo(os.path.join(WEB, "index.html"))
        if partes[0] == "web" and len(partes) == 2 and "/" not in partes[1] and not partes[1].startswith("."):
            return self.archivo(os.path.join(WEB, partes[1]))
        if partes == ["api", "salud"]:
            return self.json({"faltan": faltan_programas(), "ocupado": TRABAJO.locked()})
        if partes == ["api", "proyectos"]:
            os.makedirs(PROYECTOS, exist_ok=True)
            lista = []
            for pid in sorted(os.listdir(PROYECTOS), key=lambda d: -os.path.getmtime(os.path.join(PROYECTOS, d))):
                pr = proyecto(pid)
                if pr:
                    c, e = pr.leer("config.json", {}), pr.leer("estado.json", {})
                    lista.append({"id": pid, "nombre": c.get("nombre"), "fase": e.get("fase")})
            return self.json(lista)
        if len(partes) >= 3 and partes[0] == "api" and partes[1] == "p":
            pr = proyecto(partes[2])
            if not pr:
                return self.json({"error": "proyecto no encontrado"}, 404)
            if len(partes) == 3:
                return self.json(resumen(pr, partes[2]))
            if len(partes) == 5 and partes[3] == "muestra" and partes[4].isdigit():
                plan = pr.leer("plan.json")
                v = int(partes[4])
                if not plan or v >= len(plan["voces"]):
                    return self.json({"error": "sin muestra"}, 404)
                dst = pr.p(f"muestra{v}.mp3")
                if not os.path.exists(dst):
                    a, b = plan["voces"][v]["muestra"]
                    run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", pr.p("audio48k.wav"), "-b:a", "128k", dst])
                return self.archivo(dst)
        if len(partes) >= 3 and partes[0] == "archivos":
            pr = proyecto(partes[1])
            if pr:
                ruta = os.path.realpath(pr.p(*partes[2:]))
                if ruta.startswith(os.path.realpath(pr.dir) + os.sep):
                    return self.archivo(ruta)
        self.json({"error": "no encontrado"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        partes = [x for x in u.path.strip("/").split("/") if x]
        if partes == ["api", "subir"]:
            nombre = os.path.basename(q.get("nombre", ["video.mp4"])[0])
            ext = os.path.splitext(nombre)[1].lower() or ".mp4"
            pid = secrets.token_hex(6)
            pr = Proyecto(os.path.join(PROYECTOS, pid))
            self.guardar_cuerpo(pr.p("original" + ext))
            try:
                ancho, alto, dur = probe(pr.p("original" + ext))
            except Exception:
                shutil.rmtree(pr.dir, ignore_errors=True)
                return self.json({"error": "No pude leer ese vídeo. ¿Es un archivo de vídeo?"}, 400)
            fotograma(pr.p("original" + ext), min(dur * 0.1, 60), pr.p("fotograma.jpg"))
            pr.guardar("config.json", {"video": "original" + ext, "nombre": os.path.splitext(nombre)[0][:60],
                                       "ancho": ancho, "alto": alto, "duracion": dur, "personas": [], "partes": 1,
                                       "idioma": "es", "modelo": "turbo", "subtitulos_quemados": False,
                                       "musica_donde": "auto", "correcciones": {}})
            pr.estado("nuevo", "Vídeo subido", 0)
            return self.json(resumen(pr, pid))
        if len(partes) == 4 and partes[:2] == ["api", "p"]:
            pr = proyecto(partes[2])
            if not pr:
                return self.json({"error": "proyecto no encontrado"}, 404)
            accion = partes[3]
            if accion == "config":
                cfg = pr.leer("config.json", {})
                nuevo = self.cuerpo_json()
                permitido = {"personas", "partes", "nombre", "idioma", "modelo", "vocabulario", "subtitulos_quemados",
                             "musica_donde", "correcciones", "margen", "mantener"}
                cfg.update({k: v for k, v in nuevo.items() if k in permitido})
                pr.guardar("config.json", cfg)
                return self.json(resumen(pr, partes[2]))
            if accion == "plan":                       # el usuario ajusta cortes o qué voz es de quién
                plan = pr.leer("plan.json")
                nuevo = self.cuerpo_json()
                if "cortes" in nuevo:
                    plan["cortes"] = sorted(float(t) for t in nuevo["cortes"] if 0 < float(t) < plan["duracion"])
                if "voces" in nuevo:
                    for v, persona in enumerate(nuevo["voces"]):
                        plan["voces"][v]["persona"] = int(persona)
                pr.guardar("plan.json", plan)
                return self.json(resumen(pr, partes[2]))
            if accion == "musica":
                nombre = os.path.basename(q.get("nombre", ["musica.mp3"])[0])
                dst = "musica" + (os.path.splitext(nombre)[1].lower() or ".mp3")
                self.guardar_cuerpo(pr.p(dst))
                cfg = pr.leer("config.json", {})
                cfg["musica"] = dst
                pr.guardar("config.json", cfg)
                return self.json(resumen(pr, partes[2]))
            if accion in ("analizar", "renderizar"):
                if accion == "analizar" and len(pr.leer("config.json", {}).get("personas", [])) < 1:
                    return self.json({"error": "Marca al menos una persona en el fotograma."}, 400)
                ok = lanzar(pr, pipeline.analizar if accion == "analizar" else pipeline.renderizar, accion)
                if not ok:
                    return self.json({"error": "Ya hay otra tarea en marcha. Espera a que termine."}, 409)
                return self.json(resumen(pr, partes[2]))
        self.json({"error": "no encontrado"}, 404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--no-abrir", action="store_true")
    a = ap.parse_args()
    faltan = faltan_programas()
    if faltan:
        print("Falta instalar:", ", ".join(faltan), "→ en Mac: brew install ffmpeg")
    os.makedirs(PROYECTOS, exist_ok=True)
    for pid in os.listdir(PROYECTOS):           # tareas cortadas al cerrar la app
        pr = proyecto(pid)
        if pr and (pr.leer("estado.json", {}) or {}).get("fase") in ("analizar", "renderizar"):
            pr.estado("error", "Se interrumpió al cerrar la app", None, "Vuelve a lanzarlo: lo ya hecho no se repite.")
    url = f"http://127.0.0.1:{a.puerto}"
    srv = ThreadingHTTPServer(("127.0.0.1", a.puerto), Manejador)   # solo accesible desde este ordenador
    print(f"Entrevista Vertical en {url}  (Ctrl+C para salir)")
    if not a.no_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
