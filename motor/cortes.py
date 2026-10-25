"""Dónde partir el vídeo: en pausas al final de una frase, cerca de partes iguales, en el instante más silencioso."""
import re

import numpy as np


def _silencio_minimo(x, sr, a, b):
    a, b = max(0, int(a * sr)), int(b * sr)
    seg = x[a:b]
    if len(seg) < sr // 20:
        return (a + b) / 2 / sr, 1.0
    w = sr // 20
    r = np.sqrt(np.convolve(seg ** 2, np.ones(w) / w, "valid"))[:: sr // 100]
    i = int(r.argmin())
    return a / sr + i / 100 + 0.025, float(r[i])


def proponer(words, audio, sr, duracion, partes):
    """Devuelve `partes - 1` tiempos de corte."""
    if partes <= 1:
        return []
    cand = []
    for a, b in zip(words, words[1:]):
        hueco = b["start"] - a["end"]
        fin_frase = bool(re.search(r"[.?!]$", a["w"]))
        if fin_frase or hueco > 0.5:
            cand.append({"t0": a["end"], "t1": b["start"], "hueco": hueco, "frase": fin_frase})
    nivel = np.sqrt(np.mean(audio ** 2)) + 1e-9
    cortes = []
    for k in range(1, partes):
        objetivo = duracion * k / partes
        ventana = duracion / partes * 0.15
        mejores = [c for c in cand if abs((c["t0"] + c["t1"]) / 2 - objetivo) < ventana] or cand
        def puntos(c):
            t, rms = _silencio_minimo(audio, sr, c["t0"] - 0.3, c["t1"] + 0.3)
            return (abs(t - objetivo) / ventana) + (0 if c["frase"] else 0.6) - min(c["hueco"], 1.5) * 0.5 + rms / nivel * 0.8, t
        _, t = min((puntos(c) for c in mejores), key=lambda x: x[0])
        cortes.append(round(t, 2))
    return sorted(cortes)


def contexto(words, t, n=12):
    """Las palabras justo antes y justo después de un corte, para enseñarlo en la interfaz."""
    antes = [w["w"] for w in words if w["end"] <= t][-n:]
    despues = [w["w"] for w in words if w["start"] >= t][:n]
    return " ".join(antes), " ".join(despues)
