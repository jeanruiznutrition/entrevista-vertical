"""Utilidades compartidas: rutas, ffmpeg, estado del proyecto y codificador de vídeo."""
import functools
import json
import os
import platform
import shutil
import subprocess
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUENTES = os.path.join(RAIZ, "fuentes")
MODELOS = os.path.join(RAIZ, "modelos")

# ffmpeg de Homebrew en Mac aunque la terminal no tenga el PATH configurado
for _p in ("/opt/homebrew/bin", "/usr/local/bin"):
    if os.path.isdir(_p) and _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, **kw)


def probe(path):
    """(ancho, alto, duración) del vídeo."""
    info = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height:format=duration", "-of", "json", path]).stdout)
    st = info["streams"][0]
    return st["width"], st["height"], float(info["format"]["duration"])


@functools.lru_cache(None)
def encoder_ok(name):
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.2", "-c:v", name, "-f", "null", "-"],
                       capture_output=True)
    return r.returncode == 0


def venc(calidad="final"):
    """Argumentos de vídeo: NVIDIA, Mac (VideoToolbox) o CPU."""
    if encoder_ok("h264_nvenc"):
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20" if calidad == "final" else "28", "-b:v", "0"]
    if platform.system() == "Darwin" and encoder_ok("h264_videotoolbox"):
        return ["-c:v", "h264_videotoolbox", "-b:v", "10M" if calidad == "final" else "3M", "-allow_sw", "1"]
    return ["-c:v", "libx264", "-preset", "medium" if calidad == "final" else "veryfast", "-crf", "20" if calidad == "final" else "28"]


def faltan_programas():
    return [p for p in ("ffmpeg", "ffprobe") if not shutil.which(p)]


class Proyecto:
    """Una carpeta por vídeo: proyectos/<id>/ con config.json, estado.json y los archivos de trabajo."""

    def __init__(self, carpeta):
        self.dir = carpeta
        os.makedirs(carpeta, exist_ok=True)

    def p(self, *partes):
        return os.path.join(self.dir, *partes)

    def leer(self, nombre, defecto=None):
        try:
            with open(self.p(nombre), encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return defecto

    def guardar(self, nombre, datos):
        tmp = self.p(nombre + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p(nombre))

    def estado(self, fase, paso, progreso=None, error=None):
        e = self.leer("estado.json", {}) or {}
        log = e.get("log", [])
        if not log or log[-1] != paso:
            log.append(paso)
        self.guardar("estado.json", {"fase": fase, "paso": paso, "progreso": progreso, "error": error,
                                     "log": log[-30:], "t": time.time()})
