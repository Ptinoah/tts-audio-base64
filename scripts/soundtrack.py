"""Musique de fond, bruitages et mixage « voix d'abord », générés par code (numpy uniquement).

Rien n'est téléchargé : chaque son est synthétisé (cordes pincées, piano électrique, nappes,
batterie lo-fi, bruitages). Le résultat est simple mais propre, pensé pour passer sous une voix.

Thèmes musicaux (MUSIC_STYLES) :
  pizzicato : cordes pincées espiègles sur un beat lo-fi doux (≈100 bpm)
  lofi      : accords de piano électrique jazzy, beat lent et chaloupé, craquements de vinyle (≈80 bpm)
  ambient   : nappes chaudes et lentes, sans percussion
  upbeat    : arpège pincé et beat plus franc, énergique (≈118 bpm)

Bruitages (SFX) : shimmer, pop, clap, thud, footsteps, swoosh, whoosh, ding, click.
"""
import deps

(np,) = deps.ensure("numpy")  # installé à la demande si absent (premier lancement)

SR = 48000  # fréquence du mixage final
MUSIC_STYLES = ("pizzicato", "lofi", "ambient", "upbeat")
SFX_NAMES = ("shimmer", "pop", "clap", "thud", "footsteps", "swoosh", "whoosh", "ding", "click")

SFX_HELP = {
    "shimmer": "scintillement électronique doux (écran qui s'allume, apparition magique)",
    "pop": "petite bulle qui éclate",
    "clap": "claquement sec (mains, ordinateur portable qu'on referme)",
    "thud": "choc sourd (objet posé, porte qui se ferme)",
    "footsteps": "quelques pas rapides",
    "swoosh": "souffle court (porte, passage rapide)",
    "whoosh": "souffle long et grave (transition)",
    "ding": "petite cloche (notification, idée)",
    "click": "clic sec (souris, interrupteur)",
}


# ------------------------------------------------------------------ outils de base

def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _env(n, attack=0.005, decay=0.3, sustain=0.0, release=None):
    """Enveloppe attaque + décroissance exponentielle (+ palier optionnel)."""
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    d = sustain + (1 - sustain) * np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4))
    e = a * d
    if release:
        r = int(release * SR)
        if 0 < r < n:
            e[-r:] *= np.linspace(1, 0, r)
    return e


def _fft_filter(x, low=None, high=None, slope=2.0):
    """Filtre passe-bande doux appliqué dans le domaine fréquentiel (sans scipy)."""
    n = len(x)
    if n == 0:
        return x
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = np.ones_like(f)
    if high:
        g /= np.sqrt(1 + (f / high) ** (2 * slope))
    if low:
        with np.errstate(divide="ignore"):
            g /= np.sqrt(1 + (low / np.maximum(f, 1e-3)) ** (2 * slope))
    return np.fft.irfft(spec * g, n)


def _noise(n, rng):
    return rng.standard_normal(n)


def resample(x, sr_in, sr_out=SR):
    """Rééchantillonnage par FFT (exact pour un signal à bande limitée)."""
    if sr_in == sr_out or len(x) == 0:
        return x.astype(np.float64)
    n_out = int(round(len(x) * sr_out / sr_in))
    spec = np.fft.rfft(x)
    out_spec = np.zeros(n_out // 2 + 1, dtype=complex)
    m = min(len(spec), len(out_spec))
    out_spec[:m] = spec[:m]
    return np.fft.irfft(out_spec, n_out) * (n_out / len(x))


def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _place(buf, sig, start):
    i = int(start * SR)
    if i >= len(buf) or i + len(sig) <= 0:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[:j - i]


# ------------------------------------------------------------------ instruments

def pluck(freq, dur, rng, bright=1.0, decay=0.35):
    """Corde pincée (pizzicato) : partiels dont les aigus s'éteignent plus vite + petit bruit d'attaque."""
    t = _t(dur)
    out = np.zeros_like(t)
    for k in range(1, 12):
        fk = freq * k * (1 + 0.0004 * k * k)  # légère inharmonicité
        if fk > SR / 2.2:
            break
        amp = (1 / k ** 1.1) * (bright if k > 3 else 1)
        out += amp * np.sin(2 * np.pi * fk * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t * (1 + 0.9 * k) / decay)
    attack = _fft_filter(_noise(len(t), rng), low=1500, high=6000) * np.exp(-t / 0.006) * 0.15
    out = (out + attack) * np.clip(t / 0.002, 0, 1)
    return out / (np.max(np.abs(out)) + 1e-9)


def epiano(freq, dur, rng):
    """Piano électrique (synthèse FM type Rhodes) : corps doux + « tine » brillant à l'attaque."""
    t = _t(dur)
    idx = 1.6 * np.exp(-t / 0.25) + 0.2
    body = np.sin(2 * np.pi * freq * t + idx * np.sin(2 * np.pi * freq * t))
    tine = 0.25 * np.sin(2 * np.pi * freq * 4 * t + 2 * np.exp(-t / 0.05) * np.sin(2 * np.pi * freq * 14 * t))
    tine *= np.exp(-t / 0.08)
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return (body + tine) * _env(len(t), 0.004, 1.1, release=0.15) * trem


def pad(freq, dur, rng):
    """Nappe chaude : sinus légèrement désaccordés, attaque et extinction lentes."""
    t = _t(dur)
    out = np.zeros_like(t)
    for det in (-0.006, -0.002, 0.003, 0.007):
        for k, a in ((1, 1.0), (2, 0.35), (3, 0.12)):
            out += a * np.sin(2 * np.pi * freq * k * (1 + det) * t + rng.uniform(0, 6.28))
    e = np.minimum(np.clip(t / (dur * 0.35), 0, 1), np.clip((dur - t) / (dur * 0.35), 0, 1))
    return out * e / 4


def kick(rng, punch=1.0):
    t = _t(0.35)
    f = 48 + 90 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / (0.16 * punch)) + 0.08 * _noise(len(t), rng) * np.exp(-t / 0.004)


def snare(rng, soft=True):
    t = _t(0.25)
    body = 0.5 * np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.04)
    nz = _fft_filter(_noise(len(t), rng), low=1200, high=4000 if soft else 8000) * np.exp(-t / (0.045 if soft else 0.08))
    return (body + 0.9 * nz / (np.max(np.abs(nz)) + 1e-9)) * 0.8


def hat(rng, open_=False):
    t = _t(0.25 if open_ else 0.06)
    nz = _fft_filter(_noise(len(t), rng), low=7000)
    return nz / (np.max(np.abs(nz)) + 1e-9) * np.exp(-t / (0.08 if open_ else 0.015)) * 0.5


def crackle(n, rng, density=6.0):
    """Craquements de vinyle + souffle discret."""
    out = 0.004 * _fft_filter(_noise(n, rng), low=800, high=6000)
    pops = rng.random(n) < density / SR
    imp = np.zeros(n)
    imp[pops] = rng.uniform(-1, 1, pops.sum()) * rng.uniform(0.05, 0.25, pops.sum())
    return out + _fft_filter(imp, low=1000, high=8000)


# ------------------------------------------------------------------ thèmes musicaux

# progressions (notes MIDI des accords) ; tonalités claires et « sympas »
PROG_MAJOR = [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]]           # C  Am F  G
PROG_JAZZ = [[50, 53, 57, 60], [55, 59, 62, 65], [48, 52, 55, 59], [57, 60, 64, 67]]  # Dm7 G7 Cmaj7 Am7
PROG_AMBIENT = [[48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 62]]


def _beat(n_bars, bpm, rng, style):
    beat = 60 / bpm
    bar = 4 * beat
    out = np.zeros(int(n_bars * bar * SR) + SR)
    swing = 0.06 * beat if style in ("lofi", "pizzicato") else 0.0
    for b in range(n_bars):
        t0 = b * bar
        for q in range(4):
            tq = t0 + q * beat
            if q in (0, 2) or (style == "upbeat" and q == 3 and b % 2):
                _place(out, kick(rng, 1.2 if style == "upbeat" else 1.0) * 0.9, tq)
            if style == "lofi" and q == 2 and b % 2 == 1:
                _place(out, kick(rng) * 0.6, tq + beat / 2 + swing)
            if q in (1, 3):
                _place(out, snare(rng, soft=style != "upbeat") * (0.3 if style != "upbeat" else 0.45), tq)
            for e in (0, 1):  # croches, la deuxième légèrement retardée (swing)
                level = 0.22 if e == 0 else 0.14
                _place(out, hat(rng, open_=(style == "upbeat" and e == 1 and q == 3)) * level,
                       tq + e * (beat / 2 + swing))
    return out


def _melody_pizz(n_bars, bpm, rng, prog):
    """Motif espiègle en croches avec silences, sur les notes des accords, une octave au-dessus."""
    beat = 60 / bpm
    out = np.zeros(int(n_bars * 4 * beat * SR) + 2 * SR)
    motif = [1, 0, 1, 1, 0, 1, 0, 1]  # rythme de base, varié aléatoirement par mesure
    for b in range(n_bars):
        chord = prog[b % len(prog)]
        tones = [m + 12 for m in chord] + [chord[0] + 24]
        pattern = [x if rng.random() > 0.15 else 1 - x for x in motif]
        prev = rng.integers(len(tones))
        for i, on in enumerate(pattern):
            if not on:
                continue
            step = rng.choice([-1, 0, 1, 1, 2])
            prev = int(np.clip(prev + step, 0, len(tones) - 1))
            vel = 0.75 if i % 2 == 0 else 0.55
            _place(out, pluck(_midi(tones[prev]), 0.5, rng, decay=0.22) * vel, (b * 4 + i / 2) * beat)
        # basse pizz sur la fondamentale, temps 1 et 3
        for q in (0, 2):
            _place(out, pluck(_midi(chord[0] - 12), 0.8, rng, bright=0.5, decay=0.4) * 0.9, (b * 4 + q) * beat)
    return out


def _arp_upbeat(n_bars, bpm, rng, prog):
    beat = 60 / bpm
    out = np.zeros(int(n_bars * 4 * beat * SR) + 2 * SR)
    for b in range(n_bars):
        chord = prog[b % len(prog)]
        seq = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12] * 4
        for i, m in enumerate(seq):
            _place(out, pluck(_midi(m), 0.3, rng, bright=1.2, decay=0.15) * (0.7 if i % 4 == 0 else 0.5),
                   (b * 4 + i / 4) * beat)
        for q in range(4):
            _place(out, pluck(_midi(chord[0] - 12), 0.4, rng, bright=0.6, decay=0.25) * 0.8, (b * 4 + q) * beat)
    return out


def _chords(n_bars, bpm, rng, prog, voice_fn, length_beats=4, offset=0.0):
    beat = 60 / bpm
    out = np.zeros(int(n_bars * 4 * beat * SR) + 3 * SR)
    for b in range(n_bars):
        chord = prog[b % len(prog)]
        for m in chord:
            _place(out, voice_fn(_midi(m), length_beats * beat + 0.4, rng) * 0.35,
                   (b * 4) * beat + offset + rng.uniform(0, 0.015))
    return out


def music(style, duration, seed=0, bpm=None):
    """Génère `duration` secondes de musique (mono, SR), avec fondu d'entrée et de sortie."""
    if style not in MUSIC_STYLES:
        raise ValueError(f"thème inconnu : {style} ({', '.join(MUSIC_STYLES)})")
    rng = np.random.default_rng(seed)
    bpm = bpm or {"pizzicato": 100, "lofi": 80, "ambient": 60, "upbeat": 118}[style]
    n_bars = int(np.ceil(duration / (4 * 60 / bpm))) + 1
    if style == "pizzicato":
        layers = [(_melody_pizz(n_bars, bpm, rng, PROG_MAJOR), 1.0),
                  (_chords(n_bars, bpm, rng, PROG_MAJOR, pad), 0.25),
                  (_beat(n_bars, bpm, rng, style), 0.4)]
    elif style == "lofi":
        layers = [(_chords(n_bars, bpm, rng, PROG_JAZZ, epiano, offset=0.02), 1.0),
                  (_beat(n_bars, bpm, rng, style), 0.45)]
    elif style == "ambient":
        layers = [(_chords(n_bars, bpm, rng, PROG_AMBIENT, pad), 1.0)]
    else:
        layers = [(_arp_upbeat(n_bars, bpm, rng, PROG_MAJOR), 1.0),
                  (_chords(n_bars, bpm, rng, PROG_MAJOR, pad), 0.2),
                  (_beat(n_bars, bpm, rng, style), 0.5)]
    n = int(duration * SR)
    mix = np.zeros(n)
    for sig, gain in layers:
        sig = sig[:n] if len(sig) >= n else np.pad(sig, (0, n - len(sig)))
        mix += gain * sig / (np.sqrt(np.mean(sig ** 2)) + 1e-9)
    if style in ("pizzicato", "lofi"):
        c = crackle(n, rng)  # à peine audible : ~30 dB sous la musique
        mix += c / (np.sqrt(np.mean(c ** 2)) + 1e-12) * np.sqrt(np.mean(mix ** 2)) * 10 ** (-30 / 20)
        mix = _fft_filter(mix, low=40, high=6500 if style == "lofi" else 9000, slope=1.5)
    else:
        mix = _fft_filter(mix, low=35)
    mix = np.tanh(mix / (np.max(np.abs(mix)) + 1e-9) * 1.3)  # légère saturation « bande »
    fade_in, fade_out = min(1.0, duration / 4), min(2.0, duration / 3)
    mix[:int(fade_in * SR)] *= np.linspace(0, 1, int(fade_in * SR))
    mix[n - int(fade_out * SR):] *= np.linspace(1, 0, int(fade_out * SR))
    return mix / (np.max(np.abs(mix)) + 1e-9)


# ------------------------------------------------------------------ bruitages

def sfx(name, seed=0, count=None):
    """Retourne le bruitage `name` (mono, SR, crête à 1)."""
    rng = np.random.default_rng(seed + sum(map(ord, name)))  # stable d'une exécution à l'autre
    if name == "shimmer":
        t = _t(1.3)
        out = np.zeros_like(t)
        for i in range(9):
            f = rng.uniform(1800, 5200)
            start = i * 0.06
            e = np.clip((t - start) / 0.05, 0, 1) * np.exp(-np.maximum(t - start, 0) / 0.45)
            out += np.sin(2 * np.pi * f * t) * e * (1 + 0.5 * np.sin(2 * np.pi * rng.uniform(6, 11) * t))
        air = _fft_filter(_noise(len(t), rng), low=6000) * 0.15 * np.sin(np.pi * np.clip(t / 1.0, 0, 1))
        out = out / 9 + air
    elif name == "pop":
        t = _t(0.12)
        f = 280 + 1100 * (1 - np.exp(-t / 0.012))  # « bloup » qui monte, comme une bulle
        out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.03)
        out += 0.3 * _fft_filter(_noise(len(t), rng), low=2000) * np.exp(-t / 0.003)
    elif name == "clap":
        t = _t(0.35)
        nz = _fft_filter(_noise(len(t), rng), low=800, high=3500)
        e = np.zeros_like(t)
        for k, d in enumerate((0.0, 0.009, 0.019, 0.027)):
            e += (0.6 if k < 3 else 1.0) * np.clip((t - d) / 0.001, 0, 1) * np.exp(-np.maximum(t - d, 0) / (0.006 if k < 3 else 0.09))
        out = nz * e + 0.6 * np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.06)  # petit choc grave
    elif name == "thud":
        t = _t(0.4)
        f = 55 + 60 * np.exp(-t / 0.02)
        out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)
        out += 0.3 * _fft_filter(_noise(len(t), rng), high=900) * np.exp(-t / 0.03)
    elif name == "footsteps":
        n = count or 5
        gap = 0.27
        out = np.zeros(int((n * gap + 0.3) * SR))
        for i in range(n):
            t = _t(0.2)
            step = 0.8 * np.sin(2 * np.pi * (70 + rng.uniform(-8, 8)) * t) * np.exp(-t / 0.035)
            step += _fft_filter(_noise(len(t), rng), low=300, high=3000) * np.exp(-t / 0.025) * 0.5
            _place(out, step * rng.uniform(0.7, 1.0) * (1 if i % 2 else 0.85), i * gap + rng.uniform(-0.015, 0.015))
    elif name in ("swoosh", "whoosh"):
        dur = 0.55 if name == "swoosh" else 1.1
        t = _t(dur)
        base = _noise(len(t), rng)
        bands = [(200, 500), (400, 1000), (800, 2000), (1500, 3500), (3000, 7000)]
        filt = [_fft_filter(base, low=lo, high=hi, slope=3) for lo, hi in bands]
        pos = np.sin(np.pi * t / dur) * (len(bands) - 1) * (0.9 if name == "swoosh" else 0.6)
        out = np.zeros_like(t)
        for i, b in enumerate(filt):
            out += b * np.clip(1 - np.abs(pos - i), 0, 1)
        out *= np.sin(np.pi * t / dur) ** 2
    elif name == "ding":
        t = _t(1.5)
        out = sum(a * np.sin(2 * np.pi * 1320 * r * t) * np.exp(-t / d)
                  for r, a, d in ((1, 1, 0.7), (2.76, 0.5, 0.35), (5.4, 0.25, 0.18), (8.93, 0.12, 0.1)))
        out *= np.clip(t / 0.002, 0, 1)
    elif name == "click":
        t = _t(0.05)
        out = _fft_filter(_noise(len(t), rng), low=2000, high=9000) * np.exp(-t / 0.004)
        out += 0.4 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t / 0.006)
    else:
        raise ValueError(f"bruitage inconnu : {name} ({', '.join(SFX_NAMES)})")
    out = np.asarray(out, dtype=np.float64)
    return out / (np.max(np.abs(out)) + 1e-9)


# ------------------------------------------------------------------ mixage

def _rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def voice_envelope(voice, attack=0.02, release=0.35, frame=0.01):
    """Enveloppe 0..1 indiquant où la voix parle (lissée), à la fréquence SR."""
    hop = int(frame * SR)
    n_frames = int(np.ceil(len(voice) / hop))
    padded = np.pad(voice, (0, n_frames * hop - len(voice)))
    rms = np.sqrt(np.mean(padded.reshape(n_frames, hop) ** 2, axis=1))
    active = (rms > 0.1 * (np.percentile(rms, 95) + 1e-9)).astype(float)
    env = np.zeros(n_frames)
    a, r = np.exp(-frame / attack), np.exp(-frame / release)
    level = 0.0
    for i, v in enumerate(active):
        level = (a if v > level else r) * level + (1 - (a if v > level else r)) * v
        env[i] = level
    return np.repeat(env, hop)[:len(voice)]


def mix(voice, music_track=None, sfx_track=None, music_db=-20.0, gap_db=-12.0, sfx_db=-6.0):
    """Mixage « voix d'abord ».

    music_db : niveau (RMS) de la musique pendant que la voix parle, relatif au niveau de la voix ;
    gap_db   : niveau de la musique dans les silences (intro, pauses, fin) ;
    sfx_db   : crête des bruitages relative à la crête de la voix.
    La musique est atténuée automatiquement sous la voix (ducking), avec des transitions douces.
    Retourne (mix, stems) avec stems = {voice, music, sfx} déjà aux niveaux du mix.
    """
    n = len(voice)
    active = voice_envelope(voice)
    voiced = voice[active > 0.5]
    v_rms = np.sqrt(np.mean(voiced ** 2)) if len(voiced) else np.sqrt(np.mean(voice ** 2)) + 1e-9
    stems = {"voice": voice.copy()}
    out = voice.copy()
    if music_track is not None:
        m = music_track[:n] if len(music_track) >= n else np.pad(music_track, (0, n - len(music_track)))
        m_rms = np.sqrt(np.mean(m[np.abs(m) > 1e-4] ** 2)) + 1e-9
        gain_db = gap_db + (music_db - gap_db) * active
        m = m / m_rms * v_rms * 10 ** (gain_db / 20)
        stems["music"] = m
        out = out + m
    if sfx_track is not None and np.any(sfx_track):
        s = sfx_track[:n] if len(sfx_track) >= n else np.pad(sfx_track, (0, n - len(sfx_track)))
        s = s * (np.max(np.abs(voice)) + 1e-9) * 10 ** (sfx_db / 20)
        stems["sfx"] = s
        out = out + s
    peak = np.max(np.abs(out)) + 1e-9
    norm = 10 ** (-1 / 20) / peak  # crête à -1 dBFS
    out = out * norm
    for k in stems:
        stems[k] = stems[k] * norm
    return out, stems
