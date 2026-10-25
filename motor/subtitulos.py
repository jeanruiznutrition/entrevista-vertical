"""Subtítulos: trozos de 1-3 palabras con una palabra clave por frase, en PNG (para quemarlos) o en .srt."""
import os
import re
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .comun import FUENTES

PARADAS = set("""porque entonces también cuando siempre nosotros ustedes estamos estaba tenemos tienen hacer puede pueden
mucho muchos muchas mismo misma todos todas nuestra nuestro bueno digamos realmente justamente básicamente cualquier
alguien algunos algunas había habían hemos solamente""".split())
limpia = lambda s: re.sub(r"[^\wáéíóúñü]", "", s.lower())


def corregir(words, correcciones):
    """correcciones: {"Giancarlo": "Jean Carlos", ...} — sustituye texto en cada palabra (sin tocar los tiempos)."""
    if not correcciones:
        return words
    out = []
    for w in words:
        t = w["w"]
        for mal, bien in correcciones.items():
            if mal.strip():
                t = re.sub(re.escape(mal.strip()), bien.strip(), t, flags=re.I)
        out.append({**w, "w": t})
    return out


def trozos(words):
    caps, cur = [], []

    def cerrar():
        if cur:
            caps.append({"words": list(cur)})
        cur.clear()

    for i, w in enumerate(words):
        hueco = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 9
        cur.append(w)
        if len(cur) >= 3 or len(" ".join(x["w"] for x in cur)) >= 18 or re.search(r"[.?!,;:]$", w["w"]) or hueco > 0.5:
            cerrar()
    cerrar()

    out, frase = [], []

    def cerrar_frase():
        ws = [(ci, w) for ci, c in enumerate(frase) for w in c["words"]]
        cand = [(len(limpia(w["w"])), ci, w) for ci, w in ws if len(limpia(w["w"])) >= 7 and limpia(w["w"]) not in PARADAS]
        partes = frase
        if len(ws) >= 6 and cand:
            _, ci, kw = max(cand, key=lambda x: x[0])
            c = frase[ci]["words"]
            j = c.index(kw)
            nuevo = [{"words": p, "key": k} for p, k in ((c[:j], False), ([kw], True), (c[j + 1:], False)) if p]
            partes = frase[:ci] + nuevo + frase[ci + 1:]
        out.extend(partes)
        frase.clear()

    for c in caps:
        frase.append(c)
        if re.search(r"[.?!]$", c["words"][-1]["w"]):
            cerrar_frase()
    cerrar_frase()

    res = []
    for c in out:
        ws = c["words"]
        txt = " ".join(w["w"] for w in ws)
        res.append({"text": txt.strip(",;:.?!¿¡") if c.get("key") else txt.strip(",;:"), "raw": txt, "key": bool(c.get("key")),
                    "start": ws[0]["start"], "end": ws[-1]["end"]})
    for a, b in zip(res, res[1:]):
        a["end"] = min(b["start"], a["end"] + 0.35)
    for c in res:
        c["end"] = max(c["end"], c["start"] + 0.4)
    return res


def _hms(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(caps, inicio, fin, dst):
    """Frases completas (no trozos) para subtítulos que se activan en YouTube o Facebook."""
    lineas, n, buf = [], 1, []
    sel = [c for c in caps if inicio <= c["start"] < fin]
    for i, c in enumerate(sel):
        buf.append(c)
        txt = " ".join(x["raw"] for x in buf)
        if len(txt) > 70 or re.search(r"[.?!]$", c["raw"]) or i == len(sel) - 1:
            lineas.append(f"{n}\n{_hms(buf[0]['start'] - inicio)} --> {_hms(min(buf[-1]['end'], fin) - inicio)}\n{txt}\n")
            n += 1
            buf = []
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))


GOOGLE_FONTS = "https://github.com/google/fonts/raw/main/ofl/"
SISTEMA = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def fuente(archivo, ruta_google, tam):
    """Fuente libre (OFL) de Google Fonts, descargada la primera vez a fuentes/. Sin internet, una del sistema."""
    dst = os.path.join(FUENTES, archivo)
    if not os.path.exists(dst):
        try:
            os.makedirs(FUENTES, exist_ok=True)
            urllib.request.urlretrieve(GOOGLE_FONTS + ruta_google, dst + ".part")
            os.replace(dst + ".part", dst)
        except Exception:
            dst = next((f for f in SISTEMA if os.path.exists(f)), None)
    return ImageFont.truetype(dst, tam) if dst else ImageFont.load_default(tam)


class Dibujo:
    """PNG 1080×1920 transparente con el subtítulo a la altura del pecho."""

    def __init__(self, y_centro=1330):
        self.y = y_centro
        self.f_txt = fuente("Rajdhani-Bold.ttf", "rajdhani/Rajdhani-Bold.ttf", 100)
        self.f_key = fuente("Anton-Regular.ttf", "anton/Anton-Regular.ttf", 128)

    def png(self, texto, clave, dst):
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        fuente, color = (self.f_key, (242, 200, 75, 255)) if clave else (self.f_txt, (255, 255, 255, 255))
        lineas, cur = [], ""
        for w in (texto.upper() if clave else texto).split():
            prueba = (cur + " " + w).strip()
            if cur and fuente.getlength(prueba) > 900:
                lineas.append(cur)
                cur = w
            else:
                cur = prueba
        lineas.append(cur)
        alto = fuente.size * 1.12
        y0 = self.y - alto * len(lineas) / 2
        sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ds, d = ImageDraw.Draw(sombra), ImageDraw.Draw(img)
        for i, ln in enumerate(lineas):
            x = (1080 - fuente.getlength(ln)) / 2
            y = y0 + i * alto
            ds.text((x, y + 6), ln, font=fuente, fill=(0, 0, 0, 200))
            d.text((x, y), ln, font=fuente, fill=color, stroke_width=6, stroke_fill=(10, 4, 15, 255))
        Image.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)), img).save(dst)


def lista_concat(caps, inicio, fin, carpeta):
    """Un PNG por subtítulo + lista ffconcat con sus duraciones (la versión de ffmpeg de Homebrew no trae libass)."""
    os.makedirs(carpeta, exist_ok=True)
    dib = Dibujo()
    vacio = os.path.join(carpeta, "vacio.png")
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(vacio)
    items, t = [], inicio
    for i, c in enumerate(x for x in caps if x["end"] > inicio and x["start"] < fin):
        s, e = max(c["start"], inicio), min(c["end"], fin)
        if s > t:
            items.append((vacio, s - t))
        p = os.path.join(carpeta, f"c{i:05d}.png")
        dib.png(c["text"], c["key"], p)
        items.append((p, e - max(s, t)))
        t = max(t, e)
    if t < fin:
        items.append((vacio, fin - t))
    lista = os.path.join(carpeta, "lista.txt")
    with open(lista, "w") as f:
        f.write("ffconcat version 1.0\n")
        for p, d in items:
            if d > 0.001:
                f.write(f"file '{p}'\nduration {d:.3f}\n")
        f.write(f"file '{vacio}'\n")
    return lista
