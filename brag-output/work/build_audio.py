"""Música + efeitos + mix. Tudo em Lá menor (pad Am-F-C-G, plucks na pentatônica), mesmo reverb, música com ducking sob a voz."""
import json, os, wave
import numpy as np

W = os.path.dirname(os.path.abspath(__file__))
SR = 44100
T = json.load(open(os.path.join(W, "timing.json"), encoding="utf-8"))
TOTAL = T["total"] + 2.5            # cauda de reverb depois do último frame
N = int(TOTAL * SR)
rng = np.random.default_rng(7)

def tt(n): return np.arange(n, dtype=np.float64) / SR

# ---------------- reverb (convolução por blocos, IR estéreo sintética)
def make_ir(sec=2.4, seed=1):
    r = np.random.default_rng(seed)
    n = int(sec * SR); t = tt(n)
    ir = r.standard_normal(n) * np.exp(-t * (6.9 / sec))        # -60 dB em `sec`
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))  # pré-atraso suave
    out = onepole_lp(ir.astype(np.float32), 5200.0).astype(np.float64)   # escurece o reverb
    return (out / np.sqrt(np.sum(out ** 2))).astype(np.float32)

def fftconv(x, ir, blk=1 << 17):
    nfft = 1 << int(np.ceil(np.log2(blk + len(ir))))
    H = np.fft.rfft(ir, nfft)
    out = np.zeros(len(x) + len(ir), dtype=np.float32)
    for s in range(0, len(x), blk):
        seg = x[s:s + blk]
        y = np.fft.irfft(np.fft.rfft(seg, nfft) * H, nfft)[: len(seg) + len(ir) - 1]
        out[s:s + len(y)] += y.astype(np.float32)
    return out[: len(x)]

def movavg(x, k):
    """média móvel centrada em O(N) (cumsum)."""
    c = np.cumsum(np.concatenate([[0.0], x.astype(np.float64)]))
    h = k // 2
    idx = np.arange(len(x))
    lo = np.clip(idx - h, 0, len(x)); hi = np.clip(idx + h + 1, 0, len(x))
    return ((c[hi] - c[lo]) / np.maximum(1, hi - lo)).astype(np.float32)

def onepole_lp(x, fc):
    """passa-baixas de um polo via kernel exponencial truncado (causal, vetorizado)."""
    a = float(np.exp(-2 * np.pi * fc / SR)); L = int(12 / (1 - a)) + 1
    k = ((1 - a) * a ** np.arange(L)).astype(np.float64)
    return np.convolve(np.asarray(x, dtype=np.float64), k)[: len(x)].astype(np.float32)

# ---------------- música: pad
CH = [  # Am9, Fmaj7, C, G(add9)
    [110.00, 164.81, 220.00, 261.63, 329.63, 493.88],
    [87.31, 130.81, 174.61, 220.00, 261.63, 329.63],
    [130.81, 196.00, 261.63, 329.63, 392.00, 523.25],
    [98.00, 146.83, 196.00, 246.94, 293.66, 440.00],
]
SEG = 8.0
pad = np.zeros(N, dtype=np.float64)
nseg = int(np.ceil(TOTAL / SEG)) + 1
for k in range(nseg):
    freqs = CH[k % 4]
    t0 = k * SEG
    dur = SEG + 3.0                                  # sobreposição p/ legato
    n = int(dur * SR); t = tt(n)
    env = np.minimum(1, t / 2.6) * np.minimum(1, (dur - t) / 2.8)
    env = env ** 1.5
    seg = np.zeros(n)
    for j, f in enumerate(freqs):
        for det, ph in ((0.997, 0.0), (1.003, 1.7)):
            vib = 1 + 0.0016 * np.sin(2 * np.pi * (0.17 + 0.03 * j) * t + ph)
            for h, ah in ((1, 1.0), (2, 0.35), (3, 0.12)):
                seg += (ah / (1 + 0.15 * j)) * np.sin(2 * np.pi * f * det * h * t * vib + ph + j)
    a = int(t0 * SR); b = min(N, a + n)
    if a >= N: continue
    pad[a:b] += (seg * env)[: b - a]
pad = onepole_lp(pad.astype(np.float32), 1900.0).astype(np.float64)
pad /= np.max(np.abs(pad))

# ---------------- música: plucks esparsos (pentatônica de Lá menor)
PENT = [440.00, 523.25, 587.33, 659.25, 783.99, 880.00, 659.25 * 2]
pl = np.zeros(N, dtype=np.float64)
beat = 0.5
for i in range(int(TOTAL / beat)):
    if rng.random() < 0.28 and i % 2 == 0:
        f = float(rng.choice(PENT)); at = i * beat
        n = int(1.6 * SR); t = tt(n)
        env = np.exp(-t * 3.2) * np.minimum(1, t / 0.004)
        v = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)) * env
        a = int(at * SR); b = min(N, a + n); pl[a:b] += v[: b - a] * rng.uniform(0.5, 1.0)
pl /= max(1e-9, np.max(np.abs(pl)))

# ---------------- sub-baixo (tônica de cada acorde)
sub = np.zeros(N, dtype=np.float64)
for k in range(nseg):
    f = CH[k % 4][0] / 2
    n = int((SEG + 1.5) * SR); t = tt(n)
    env = np.minimum(1, t / 1.5) * np.minimum(1, (SEG + 1.5 - t) / 1.8)
    v = np.sin(2 * np.pi * f * t) * env
    a = int(k * SEG * SR); b = min(N, a + n)
    if a >= N: continue
    sub[a:b] += v[: b - a]
sub /= max(1e-9, np.max(np.abs(sub)))

music_dry = (0.80 * pad + 0.16 * pl + 0.22 * sub).astype(np.float32)

# ---------------- efeitos (mesma tonalidade): swell + ping a cada início de cena
sfx = np.zeros(N, dtype=np.float64)
def swell(at, dur=0.9, level=0.5):
    n = int(dur * SR); t = tt(n)
    noise = rng.standard_normal(n)
    noise = onepole_lp(noise.astype(np.float32), 700.0).astype(np.float64)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    a = int(at * SR); b = min(N, a + n); sfx[a:b] += (noise * env)[: b - a] * level * 6
def ping(at, f, level=0.4, dec=2.6):
    n = int(2.2 * SR); t = tt(n)
    env = np.exp(-t * dec) * np.minimum(1, t / 0.003)
    v = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2.01 * f * t)) * env
    a = int(at * SR); b = min(N, a + n); sfx[a:b] += v[: b - a] * level
def tick(at, f=1318.5, level=0.12):
    n = int(0.25 * SR); t = tt(n)
    v = np.sin(2 * np.pi * f * t) * np.exp(-t * 28) * np.minimum(1, t / 0.0015)
    a = int(at * SR); b = min(N, a + n); sfx[a:b] += v[: b - a] * level

notes = [659.25, 587.33, 523.25, 659.25, 783.99, 587.33, 523.25, 880.00]
for i, sc in enumerate(T["scenes"]):
    s0 = sc["start"]
    swell(max(0, s0 - 0.25 if i else 0.0), 0.9, 0.35)
    ping(s0 + 0.35, notes[i % len(notes)], 0.30)
# momentos-chave
sc = {s["id"]: s for s in T["scenes"]}
def at(sid, k, off=0.0):
    s = sc[sid]; x = s["sentences"][k - 1]; return s["start"] + x["t0"] + off
ping(at("hook", 3, 0.3), 220.0, 0.5, 1.4); swell(at("hook", 3, -0.3), 1.3, 0.5)   # revelação do nome
for k in range(4):                                                                  # escala no gradiente
    tick(at("hook", 4, 0.6 + 0.8 * k), [659.25, 783.99, 880.0, 587.33][k], 0.18)
for k in range(10):                                                                 # nós do pipeline
    s = sc["visao"]["sentences"][1]; tick(sc["visao"]["start"] + s["t0"] + (s["t1"] - s["t0"]) * [0, 1, 2, 3, 4, 5, 6, 7, 7.7, 8.5][k] / 9.4, 1046.5 + 0 * k, 0.10)
for k in range(5):                                                                  # pesos da decisão
    s = sc["decisao"]["sentences"][2]; tick(sc["decisao"]["start"] + s["t0"] + (s["t1"] - s["t0"]) * (k + 0.2) / 5.3, [880, 988, 1047, 1175, 1319][k], 0.13)
sD = sc["decisao"]["sentences"][5]
for frac, f in ((1 / 10, 659.25), (5 / 10, 880.0)):                                  # marcador do log-odds
    ping(sc["decisao"]["start"] + sD["t0"] + (sD["t1"] - sD["t0"]) * frac + 0.3, f, 0.35)
ping(sc["fim"]["start"] + sc["fim"]["sentences"][0]["t0"] + 0.2, 440.0, 0.35, 1.2)

# ---------------- reverb bus
irL, irR = make_ir(2.4, 11), make_ir(2.4, 12)
def wet(x): return np.stack([fftconv(x, irL), fftconv(x, irR)], 1)
def dry2(x, wide=0.0):
    d = int(0.011 * SR)
    L = x; R = np.concatenate([np.zeros(d, dtype=x.dtype), x[:-d]]) if wide else x
    return np.stack([L, R * 1.0], 1)

music = 0.74 * dry2(music_dry, 1) + 0.50 * wet(music_dry)
sfx32 = sfx.astype(np.float32)
sfxm = 0.9 * dry2(sfx32) + 0.9 * wet(sfx32)

# fade-in/out da música
t = tt(N)
fade = np.minimum(1, t / 3.0) * np.minimum(1, np.maximum(0, (TOTAL - 0.5 - t)) / 5.0)
music *= fade[:, None].astype(np.float32)

# ---------------- narração + ducking
voz = np.load(os.path.join(W, "narration.npy")).astype(np.float32)
voz = np.concatenate([voz, np.zeros(max(0, N - len(voz)), dtype=np.float32)])[:N]
voz = voz / max(1e-9, np.max(np.abs(voz)))
# compressão leve (soft-knee) p/ nivelar frases
voz = np.tanh(voz * 1.6) / np.tanh(1.6)
voz *= 0.80
# presença: realce suave de 2–3 kHz (dif. de passa-baixas)
lp = onepole_lp(voz, 1800.0)
voz = voz + 0.25 * (voz - lp)
env = np.abs(voz)
env = movavg(env, int(0.18 * SR))
duck = movavg(np.clip(env / 0.05, 0, 1), int(0.5 * SR))
g = 1.0 - 0.62 * duck
def rms(x, thr=0.0):
    y = x[np.abs(x) > thr]
    return float(np.sqrt(np.mean(y.astype(np.float64) ** 2))) if len(y) else 0.0
# alvos: voz (trechos falados) RMS 0.17; música ~18 dB abaixo sob a fala (pré-ducking 0.056); efeitos com pico ~ -16 dBFS
voz = voz * (0.17 / max(1e-9, rms(voz, 0.02)))
music = music * (0.056 / max(1e-9, rms(music[:, 0])))
sfxm = sfxm * (0.16 / max(1e-9, float(np.max(np.abs(sfxm)))))
mix = np.stack([voz, voz], 1) + music * g[:, None] + sfxm * (1 - 0.3 * duck)[:, None]
print("voz rms", round(rms(voz, 0.02), 3), "music rms", round(rms(music[:, 0]), 3), "sfx pico", round(float(np.max(np.abs(sfxm))), 3), "mix pico", round(float(np.max(np.abs(mix))), 3))
peak = np.max(np.abs(mix)); mix = mix / max(peak, 1e-9) * 0.89
out = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
with wave.open(os.path.join(W, "mix.wav"), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())
print("mix.wav ok", round(TOTAL, 1), "s")
