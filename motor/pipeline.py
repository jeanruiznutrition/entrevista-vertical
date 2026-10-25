"""Las dos fases que lanza la interfaz: analizar (lento, una vez) y renderizar (se puede repetir con otros ajustes)."""
import json
import os
import traceback

import numpy as np

from . import analisis, cortes, hablantes, render, subtitulos
from .comun import probe


def _palabras(pr):
    with open(pr.p("palabras.json"), encoding="utf-8") as f:
        return json.load(f)["words"]


def analizar(pr):
    try:
        cfg = pr.leer("config.json")
        src, personas = pr.p(cfg["video"]), cfg["personas"]
        ancho, alto, dur = probe(src)
        n = len(personas)

        pr.estado("analizar", "Extrayendo el audio", 0.02)
        analisis.extraer_audio(src, pr.p("audio16k.wav"), pr.p("audio48k.wav"))

        if not os.path.exists(pr.p("palabras.json")):
            pr.estado("analizar", "Transcribiendo con Whisper (es lo más lento: en un Mac, ~1 min por cada minuto de vídeo)", 0.05)
            analisis.transcribir(pr.p("audio16k.wav"), pr.p("palabras.json"), cfg.get("idioma", "es"),
                                 cfg.get("modelo", "turbo"), cfg.get("vocabulario", ""))
        words = _palabras(pr)

        if not os.path.exists(pr.p("voces.npy")):
            pr.estado("analizar", "Reconociendo las voces", 0.6)
            analisis.huellas_de_voz(pr.p("audio16k.wav"), pr.p("voces.npy"),
                                    lambda f: pr.estado("analizar", "Reconociendo las voces", 0.6 + 0.2 * f))
        E = np.load(pr.p("voces.npy"))

        pr.estado("analizar", "Midiendo el movimiento de cada cara", 0.82)
        M = analisis.movimiento(src, analisis.cajas_de_cara(personas, ancho, alto), pr.p("movimiento.npy"))

        pr.estado("analizar", "Decidiendo quién habla en cada momento", 0.95)
        total = int(dur)
        habla = hablantes.segundos_con_voz(words, total)
        C = hablantes.agrupar_voces(E, habla, n)
        np.save(pr.p("centros.npy"), C)
        voz_a_cara, puntos = hablantes.asignar_caras(E, C, M, habla)
        audio, sr = analisis.leer_wav(pr.p("audio16k.wav"))
        propuestos = cortes.proponer(words, audio, sr, dur, cfg.get("partes", 1))
        pr.guardar("plan.json", {
            "duracion": dur, "ancho": ancho, "alto": alto,
            "voces": [{"muestra": m, "persona": voz_a_cara[v]} for v, m in enumerate(hablantes.muestras(E, C, habla))],
            "puntos_voz_cara": puntos,
            "cortes": propuestos,
            "contexto": [cortes.contexto(words, t) for t in propuestos],
            "palabras": len(words),
        })
        pr.estado("listo_para_revisar", "Análisis terminado", 1.0)
    except Exception as e:
        pr.estado("error", "Algo falló al analizar", None, f"{e}\n{traceback.format_exc()[-1500:]}")


def calcular_planos(pr):
    cfg, plan = pr.leer("config.json"), pr.leer("plan.json")
    words = _palabras(pr)
    E, C = np.load(pr.p("voces.npy")), np.load(pr.p("centros.npy"))
    voz_a_cara = [v["persona"] for v in plan["voces"]]
    habla = hablantes.segundos_con_voz(words, int(plan["duracion"]))
    lab = hablantes.por_segundo(E, C, voz_a_cara, habla, cfg.get("margen", 0.08))
    return hablantes.planos(lab, plan["duracion"], cfg.get("mantener", 3))


def renderizar(pr):
    try:
        cfg, plan = pr.leer("config.json"), pr.leer("plan.json")
        src = pr.p(cfg["video"])
        pr.estado("renderizar", "Preparando planos y subtítulos", 0.01)
        planos = calcular_planos(pr)
        pr.guardar("planos.json", planos)
        words = subtitulos.corregir(_palabras(pr), cfg.get("correcciones", {}))
        caps = subtitulos.trozos(words)
        limites = [0.0] + sorted(plan["cortes"]) + [plan["duracion"]]
        n = len(limites) - 1
        nombre = cfg.get("nombre") or "Video"
        salidas = []
        musica = pr.p(cfg["musica"]) if cfg.get("musica") else None
        for i, (a, b) in enumerate(zip(limites, limites[1:]), 1):
            base = f"{nombre} - Parte {i}" if n > 1 else nombre
            pr.estado("renderizar", f"Renderizando parte {i} de {n}", (i - 1) / n)
            lista = subtitulos.lista_concat(caps, a, b, pr.p(f"subs{i}")) if cfg.get("subtitulos_quemados") else None
            tmp = pr.p(f"parte{i}-video.mp4")
            render.video(src, cfg["personas"], plan["ancho"], plan["alto"], planos, a, b, tmp, pr.p(f"cmds{i}.txt"), lista)
            pr.estado("renderizar", f"Masterizando el audio de la parte {i}", (i - 0.15) / n)
            donde = cfg.get("musica_donde", "auto")
            if donde == "auto":   # la primera parte suele tener sintonía y la última despedida
                donde = "ambos" if 1 < i < n else ("final" if i == 1 and n > 1 else ("inicio" if i == n and n > 1 else "nada"))
            final = pr.p("salida", base + ".mp4")
            os.makedirs(pr.p("salida"), exist_ok=True)
            l, pico = render.master(tmp, final, musica, donde if musica else "nada")
            os.remove(tmp)
            subtitulos.srt(caps, a, b, pr.p("salida", base + ".srt"))
            salidas.append({"video": os.path.relpath(final, pr.dir), "srt": os.path.relpath(pr.p("salida", base + ".srt"), pr.dir),
                            "inicio": a, "fin": b, "lufs": l, "pico": pico})
        pr.guardar("salidas.json", salidas)
        pr.estado("terminado", "¡Listo!", 1.0)
    except Exception as e:
        pr.estado("error", "Algo falló al renderizar", None, f"{e}\n{traceback.format_exc()[-1500:]}")
