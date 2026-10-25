"""Análisis de la toma: audio, transcripción palabra a palabra, huella de voz cada segundo y movimiento de cada cara."""
import json
import os
import subprocess
import wave

import numpy as np

from .comun import MODELOS, run


def extraer_audio(src, dst16, dst48):
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", dst16])
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "2", "-ar", "48000", dst48])


def fotograma(src, t, dst):
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", src, "-frames:v", "1", "-q:v", "3", dst])


def leer_wav(path):
    with wave.open(path) as f:
        return np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768, f.getframerate()


def transcribir(wav16, dst, idioma="es", modelo="turbo", vocab=""):
    """Whisper en CPU (en Mac MPS no es fiable con Whisper). Guarda {"text", "words": [{w, start, end}]}."""
    import torch
    import whisper
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = whisper.load_model(modelo, device=dev)        # caché estándar de Whisper (~/.cache/whisper)
    res = m.transcribe(wav16, language=idioma, word_timestamps=True, condition_on_previous_text=False,
                       initial_prompt=vocab or None, fp16=(dev == "cuda"))
    words = [{"w": w["word"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
             for seg in res["segments"] for w in seg.get("words", []) if w["word"].strip()]
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"text": res["text"].strip(), "words": words}, f, ensure_ascii=False)
    return words


def huellas_de_voz(wav16, dst, avisar=None):
    """Una huella de voz ECAPA (192 valores, normalizada) por segundo, con ventana de 1,5 s."""
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    torch.set_num_threads(2)            # menos calor en portátiles sin ventilador
    dev = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    x, sr = leer_wav(wav16)
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         savedir=os.path.join(MODELOS, "ecapa"), run_opts={"device": dev})
    win, hop = int(1.5 * sr), sr
    starts = list(range(0, max(1, len(x) - win), hop))
    embs = []
    with torch.no_grad():
        for i in range(0, len(starts), 64):
            lote = np.stack([x[max(0, s - win // 3):][:win] for s in starts[i:i + 64]])
            e = enc.encode_batch(torch.from_numpy(lote).to(dev)).squeeze(1).cpu().numpy()
            embs.append(e / np.linalg.norm(e, axis=1, keepdims=True))
            if avisar:
                avisar(min(1.0, (i + 64) / len(starts)))
    E = np.concatenate(embs).astype(np.float32)
    np.save(dst, E)
    return E


def cajas_de_cara(personas, ancho, alto):
    """Caja alrededor de cada cara a partir del clic (x, y en proporción 0-1)."""
    w, h = int(alto * 0.22), int(alto * 0.26)
    cajas = []
    for p in personas:
        cx, cy = p["x"] * ancho, p["y"] * alto
        x0 = int(min(max(cx - w / 2, 0), ancho - w))
        y0 = int(min(max(cy - h / 2, 0), alto - h))
        cajas.append((x0, y0, w, h))
    return cajas


def movimiento(src, cajas, dst, fps=10):
    """Cuánto se mueve cada cara (media de diferencias entre fotogramas), 10 veces por segundo → [n, personas]."""
    W, H = 48, 56
    n = len(cajas)
    fc = f"[0]fps={fps},format=gray,split={n}" + "".join(f"[s{i}]" for i in range(n)) + ";"
    fc += ";".join(f"[s{i}]crop={w}:{h}:{x}:{y},scale={W}:{H}[c{i}]" for i, (x, y, w, h) in enumerate(cajas))
    fc += (";" + "".join(f"[c{i}]" for i in range(n)) + f"hstack={n}[o]") if n > 1 else ";[c0]null[o]"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-filter_complex", fc, "-map", "[o]", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    fs = W * n * H
    prev, res = None, []
    while True:
        b = p.stdout.read(fs)
        if len(b) < fs:
            break
        f = np.frombuffer(b, np.uint8).reshape(H, W * n).astype(np.int16)
        if prev is not None:
            d = np.abs(f - prev)
            res.append([d[:, i * W:(i + 1) * W].mean() for i in range(n)])
        prev = f
    p.wait()
    M = np.array(res, np.float32).reshape(-1, n)
    np.save(dst, M)
    return M
