"""Render vertical 1080×1920: un encuadre por persona o plano general con fondo desenfocado,
cambiando según quién habla (sendcmd), subtítulos opcionales encima y máster de audio a −14 LUFS."""
import json
import os
import re
import subprocess

from .comun import run, venc
from .hablantes import GENERAL


def geometria(personas, ancho, alto):
    """Recorte 9:16 por persona: la cara queda centrada y al 38 % de la altura."""
    ch = int(alto * 0.833) // 2 * 2
    cw = int(ch * 9 / 16) // 2 * 2
    out = []
    for p in personas:
        cx, cy = p["x"] * ancho, p["y"] * alto
        x0 = int(min(max(cx - cw / 2, 0), ancho - cw))
        y0 = int(min(max(cy - 0.38 * ch, 0), alto - ch))
        out.append((x0, y0))
    return cw, ch, out


def _escapa(path):
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def video(src, personas, ancho, alto, planos, inicio, fin, dst, cmds, subtitulos=None, calidad="final"):
    cw, ch, pos = geometria(personas, ancho, alto)
    sel = [s for s in planos if s["end"] > inicio and s["start"] < fin]
    lineas = []
    for s in sel:
        t = max(0.0, s["start"] - inicio)
        if s["shot"] == GENERAL:
            lineas.append(f"{t:.3f} [enter] overlay@p x 4000;")
        else:
            x0, y0 = pos[s["shot"]]
            lineas.append(f"{t:.3f} [enter] crop@p x {x0}, [enter] crop@p y {y0}, [enter] overlay@p x 0;")
    with open(cmds, "w") as f:
        f.write("\n".join(lineas) + "\n")
    primero = sel[0]["shot"] if sel else GENERAL
    x0, y0 = pos[primero] if primero != GENERAL else pos[0]
    fc = (f"[0:v]fps=30,split=3[a][b][c];"
          f"[a]scale=-2:480,crop=270:480,gblur=sigma=10,eq=brightness=-0.12,scale=1080:1920[fondo];"
          f"[b]scale=1080:-2[plano];[fondo][plano]overlay=0:(H-h)/2-120[gen];"
          f"[c]sendcmd=f='{_escapa(cmds)}',crop@p={cw}:{ch}:{x0}:{y0},scale=1080:1920:flags=lanczos,setsar=1[per];"
          f"[gen][per]overlay@p=x={4000 if primero == GENERAL else 0}:y=0[v0];")
    entradas = ["-ss", str(inicio), "-t", str(fin - inicio), "-i", src]
    if subtitulos:
        entradas += ["-f", "concat", "-safe", "0", "-i", subtitulos]
        fc += "[v0][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    else:
        fc += "[v0]format=yuv420p[v]"
    run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
         "-c:a", "aac", "-b:a", "192k", *venc(calidad), "-movflags", "+faststart", dst])


def _lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)[-1])


def master(vid, dst, musica=None, donde="nada", segundos=16, lufs=-14.0):
    """Música suave (≈19 dB bajo la voz) al inicio, al final o en ambos, y máster con limitador de pico real."""
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", vid]).stdout)
    entradas = ["-i", vid]
    pre = "[0:a]aformat=channel_layouts=stereo:sample_rates=48000,highpass=f=70"
    if musica and donde != "nada":
        ml, _ = _lufs(musica)
        g = -33 - ml
        L = min(segundos, dur / 2)
        ini = f"atrim=0:{L},volume={g:.2f}dB,afade=t=in:d=0.8,afade=t=out:st={L - 6}:d=6"
        fin = f"atrim=0:{L},volume={g:.2f}dB,afade=t=in:d=5,afade=t=out:st={L - 2.5}:d=2.5,adelay={int((dur - L) * 1000)}:all=1"
        entradas += ["-stream_loop", "-1", "-i", musica]
        if donde == "inicio":
            mus = f"[1:a]aformat=channel_layouts=stereo:sample_rates=48000,{ini}[m]"
        elif donde == "final":
            mus = f"[1:a]aformat=channel_layouts=stereo:sample_rates=48000,{fin}[m]"
        else:
            mus = (f"[1:a]aformat=channel_layouts=stereo:sample_rates=48000,asplit[m1][m2];[m1]{ini}[s];[m2]{fin}[e];"
                   f"[s][e]amix=inputs=2:normalize=0:duration=longest[m]")
        pre = f"{mus};{pre}[v];[v][m]amix=inputs=2:normalize=0:duration=first"
    r = subprocess.run(["ffmpeg", "-hide_banner", *entradas, "-filter_complex", pre + f",loudnorm=I={lufs}:TP=-2.2:LRA=11:print_format=json[o]",
                        "-map", "[o]", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
    ln = (f"loudnorm=I={lufs}:TP=-2.2:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex",
         pre + f",{ln},aresample=192000,alimiter=limit=0.76:attack=1:release=60:level=false,aresample=48000[o]",
         "-map", "0:v", "-map", "[o]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst])
    return _lufs(dst)
