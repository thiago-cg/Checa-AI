"""Monta a linha do tempo: aparas de silêncio, offsets por cena, narration.wav e timing.js."""
import json, wave, os
import numpy as np

W = os.path.dirname(os.path.abspath(__file__))
SR = 44100
LEAD = 0.9      # antes da 1ª frase da cena (título entra)
TAIL = 1.3      # depois da última frase (respiro / hold)
GAP = 0.38      # entre frases
nar = json.load(open(os.path.join(W, "narration.json"), encoding="utf-8"))

def load(path):
    w = wave.open(path)
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    assert w.getframerate() == SR and w.getnchannels() == 1
    return x

def trim(x, thr=0.012, pre=0.04, post=0.10):
    idx = np.where(np.abs(x) > thr)[0]
    a = max(0, idx[0] - int(pre * SR)); b = min(len(x), idx[-1] + int(post * SR))
    y = x[a:b].copy()
    f = int(0.012 * SR)  # micro-fade p/ evitar clique
    y[:f] *= np.linspace(0, 1, f); y[-f:] *= np.linspace(1, 0, f)
    return y

scenes, pieces, t = [], [], 0.0
for sc in nar:
    s0 = t
    lt = LEAD
    sents = []
    for i, s in enumerate(sc["sentences"], 1):
        x = trim(load(os.path.join(W, "audio", f"{sc['id']}_{i:02d}.wav")))
        d = len(x) / SR
        sents.append({"t0": round(lt, 3), "t1": round(lt + d, 3), "text": s["t"]})
        pieces.append((s0 + lt, x))
        lt += d + GAP
    dur = lt - GAP + TAIL
    scenes.append({"id": sc["id"], "start": round(s0, 3), "dur": round(dur, 3), "sentences": sents})
    t = s0 + dur

total = t
buf = np.zeros(int(total * SR) + SR, dtype=np.float32)
for at, x in pieces:
    i = int(at * SR); buf[i:i + len(x)] += x
np.save(os.path.join(W, "narration.npy"), buf)
out = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
with wave.open(os.path.join(W, "narration.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())

json.dump({"total": round(total, 3), "scenes": scenes}, open(os.path.join(W, "timing.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(os.path.join(W, "timing.js"), "w", encoding="utf-8").write("window.TIMING=" + json.dumps({"total": round(total, 3), "scenes": scenes}, ensure_ascii=False) + ";")
print("total", round(total, 1), "s =", int(total // 60), "min", round(total % 60), "s")
for s in scenes:
    print(f"{s['id']:12s} start {s['start']:7.1f}  dur {s['dur']:5.1f}")
