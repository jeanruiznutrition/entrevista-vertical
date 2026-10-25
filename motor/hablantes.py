"""Quién habla cada segundo: agrupa las huellas de voz en tantas voces como personas, asigna cada voz a una cara
(la que más se mueve cuando esa voz suena) y convierte el resultado en planos estables."""
import itertools

import numpy as np

GENERAL = -1   # plano general


def segundos_con_voz(words, total):
    habla = np.zeros(total, bool)
    for w in words:
        habla[int(w["start"]):min(total, int(w["end"]) + 1)] = True
    return habla


def _kmeans_coseno(X, k, intentos=8, seed=0):
    rng = np.random.default_rng(seed)
    mejor = None
    for _ in range(intentos):
        C = [X[rng.integers(len(X))]]
        for _ in range(1, k):                       # k-means++
            d = np.clip(1 - np.max(X @ np.stack(C).T, 1), 0, None) + 1e-9
            C.append(X[rng.choice(len(X), p=d / d.sum())])
        C = np.stack(C)
        for _ in range(30):
            lab = (X @ C.T).argmax(1)
            nuevo = np.stack([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
            nuevo /= np.linalg.norm(nuevo, axis=1, keepdims=True)
            if np.allclose(nuevo, C):
                break
            C = nuevo
        coste = -(X @ C.T).max(1).sum()
        if mejor is None or coste < mejor[0]:
            mejor = (coste, C)
    return mejor[1]


def agrupar_voces(E, habla, n):
    """Centros de voz (k-means coseno) y su refinado con los segundos más claros."""
    idx = np.where(habla[:len(E)])[0]
    X = E[idx]
    C = _kmeans_coseno(X, n) if n > 1 else X.mean(0, keepdims=True) / np.linalg.norm(X.mean(0))
    for _ in range(3):
        sim = X @ C.T
        srt = np.sort(sim, 1)
        claro = (srt[:, -1] - srt[:, -2] > 0.12) if n > 1 else np.ones(len(X), bool)
        lab = sim.argmax(1)
        C = np.stack([X[claro & (lab == j)].mean(0) if (claro & (lab == j)).sum() > 3 else C[j] for j in range(n)])
        C /= np.linalg.norm(C, axis=1, keepdims=True)
    return C


def asignar_caras(E, C, M, habla, fps=10):
    """Para cada voz, la cara que más se mueve mientras suena (mejor permutación)."""
    n = len(C)
    total = min(len(E), len(M) // fps)
    z = (M - np.median(M, 0)) / (np.percentile(M, 75, 0) - np.percentile(M, 25, 0) + 1e-6)
    zs = np.array([z[s * fps:(s + 1) * fps].mean(0) for s in range(total)])
    lab = (E[:total] @ C.T).argmax(1)
    puntos = np.zeros((n, n))
    for v in range(n):
        for c in range(n):
            act = (lab == v) & habla[:total]
            if act.any() and (~act).any():
                puntos[v, c] = zs[act, c].mean() - zs[~act & habla[:total], c].mean()
    perm = max(itertools.permutations(range(n)), key=lambda p: sum(puntos[v, p[v]] for v in range(n)))
    return list(perm), puntos.round(3).tolist()


def muestras(E, C, habla, dur=5):
    """Para cada voz, el tramo de `dur` s donde se la reconoce con más claridad (para escucharlo en la interfaz)."""
    sim = E @ C.T
    out = []
    for v in range(len(C)):
        otras = np.delete(sim, v, 1).max(1) if len(C) > 1 else np.zeros(len(E))
        marg = np.where(habla[:len(E)], sim[:, v] - otras, -1)
        s = np.convolve(marg, np.ones(dur), "valid")
        a = int(s.argmax())
        out.append([float(a), float(a + dur)])
    return out


def por_segundo(E, C, voz_a_cara, habla, margen=0.08):
    sim = E @ C.T
    res = []
    for s in range(len(habla)):
        if s >= len(E) or not habla[s]:
            res.append(None)                     # silencio: se decide después
            continue
        o = np.argsort(sim[s])[::-1]
        if len(C) > 1 and sim[s, o[0]] - sim[s, o[1]] < margen:
            res.append(GENERAL)
        else:
            res.append(voz_a_cara[int(o[0])])
    return res


def planos(etiquetas, duracion, mantener=3, silencio_general=4):
    """Planos estables: solo se cambia si el nuevo dura `mantener` s seguidos.
    Los silencios largos (música, cabeceras) van en plano general."""
    lab = list(etiquetas)
    i = 0
    while i < len(lab):                          # rellena silencios
        if lab[i] is None:
            j = i
            while j < len(lab) and lab[j] is None:
                j += 1
            relleno = GENERAL if (j - i >= silencio_general or i == 0) else lab[i - 1]
            lab[i:j] = [relleno] * (j - i)
            i = j
        else:
            i += 1
    out, actual, racha, cand = [{"start": 0.0, "shot": lab[0] if lab else GENERAL}], lab[0] if lab else GENERAL, 0, None
    for s, p in enumerate(lab):
        if p == actual:
            racha, cand = 0, None
            continue
        racha = racha + 1 if p == cand else 1
        cand = p
        if racha >= mantener:
            actual = cand
            out.append({"start": float(s - mantener + 1), "shot": actual})
            racha, cand = 0, None
    limpio = []
    for p in out:
        if limpio and limpio[-1]["shot"] == p["shot"]:
            continue
        limpio.append(p)
    for a, b in zip(limpio, limpio[1:]):
        a["end"] = b["start"]
    limpio[-1]["end"] = float(duracion)
    return limpio
