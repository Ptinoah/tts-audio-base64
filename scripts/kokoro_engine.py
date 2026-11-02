"""Moteur de voix neuronale Kokoro-82M (voix naturelle), avec téléchargement vérifié des poids.

Tout vient de registres de paquets (PyPI et npm), joignables là où pip/npm le sont :
  - kokoro-onnx + onnxruntime (PyPI) pour l'inférence et la phonétisation (espeak-ng) ;
  - les poids du modèle : paquet npm kokoro-q8-shards@1.0.0 (92 Mo, vérifié par SHA-256) ;
  - les voix : la voix française est embarquée dans assets/voices ; les autres viennent du paquet
    npm kokoro-js@1.2.1 (empreinte npm vérifiée), téléchargé seulement si on en a besoin.
Le tout est mis en cache (TTS_AUDIO_CACHE, sinon ~/.cache/tts-audio-base64).
"""
import base64
import hashlib
import io
import os
import sys
import tarfile
import urllib.request

import deps

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("TTS_AUDIO_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "tts-audio-base64")

MODEL = {
    "tarball": "https://registry.npmjs.org/kokoro-q8-shards/-/kokoro-q8-shards-1.0.0.tgz",
    "integrity": "sha512-KoJQ203LxUOFrHAm12mu+hRmvqTmOcCgz61OVgTxmxX4isWaufLCF6kYz+QwOzVFYGNS62HHJWBHUbhzeoR43g==",
    "sha256": "fbae9257e1e05ffc727e951ef9b9c98418e6d79f1c9b6b13bd59f5c9028a1478",
    "file": "kokoro-v1.0-q8.onnx",
}
VOICES_PKG = {
    "tarball": "https://registry.npmjs.org/kokoro-js/-/kokoro-js-1.2.1.tgz",
    "integrity": "sha512-oq0HZJWis3t8lERkMJh84WLU86dpYD0EuBPtqYnLlQzyFP1OkyBRDcweAqCfhNOpltyN9j/azp1H6uuC47gShw==",
}

# langue demandée -> (code de langue Kokoro/espeak, voix féminine, voix masculine)
LANGS = {
    "fr": ("fr-fr", "ff_siwis", "fm_siwis"),
    "en-us": ("en-us", "af_heart", "am_michael"),
    "en-gb": ("en-gb", "bf_emma", "bm_george"),
    "es": ("es", "ef_dora", "em_alex"),
    "it": ("it", "if_sara", "im_nicola"),
    "pt-br": ("pt-br", "pf_dora", "pm_alex"),
    "hi": ("hi", "hf_alpha", "hm_omega"),
}
ALIASES = {"fr-fr": "fr", "fr-be": "fr", "fr-ch": "fr", "fr-ca": "fr", "en": "en-us", "en-uk": "en-gb",
           "es-es": "es", "it-it": "it", "pt": "pt-br", "hi-in": "hi"}
SAMPLE_RATE = 24000

# Voix masculines françaises dérivées. Kokoro n'a qu'une voix française (féminine, ff_siwis).
# Le vecteur de style a deux moitiés : 0-127 règle le timbre (décodeur), 128-255 la prosodie
# (rythme, intonation, hauteur). Modifier la prosodie vers des voix d'homme d'autres langues
# importe leur façon de parler, perçue comme un accent : on ne touche donc JAMAIS à cette moitié.
# La voix est rendue masculine après coup par la fonction « Change gender » de Praat (hauteur et
# formants abaissés, durées et forme de l'intonation conservées), éventuellement avec un timbre
# masculin appliqué à la moitié timbre seulement (direction gender_direction.bin, cf. NOTICE.md).
# nom -> (intensité timbre, rapport de formants Praat, hauteur médiane visée en Hz)
DERIVED = {
    "fm_siwis_leger": (0.0, 0.88, 140),
    "fm_siwis": (0.0, 0.85, 120),          # défaut de --gender m : prosodie strictement identique
    "fm_siwis_grave": (0.0, 0.82, 108),
    "fm_siwis_timbre": (1.3, 0.95, 120),   # timbre masculin issu du modèle, intonation française
}


def resolve_lang(lang):
    """Retourne la clé de LANGS correspondant à --lang, ou None si Kokoro ne gère pas la langue."""
    key = lang.lower()
    key = ALIASES.get(key, key)
    return key if key in LANGS else None


def _log(msg):
    print(msg, file=sys.stderr)


def _download(url, integrity):
    """Télécharge en mémoire et vérifie l'empreinte npm (sha512 en base64)."""
    _log(f"Téléchargement de {url.rsplit('/', 1)[-1]}…")
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    algo, expected = integrity.split("-", 1)
    got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if got != expected:
        raise RuntimeError(f"empreinte inattendue pour {url} : téléchargement altéré")
    return data


def model_path():
    """Chemin du modèle ONNX en cache, téléchargé et vérifié au premier appel."""
    path = os.path.join(CACHE_DIR, MODEL["file"])
    if os.path.exists(path):
        return path
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = _download(MODEL["tarball"], MODEL["integrity"])
    parts = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = os.path.basename(member.name)
            if name.startswith("kokoro-q8.part") and name.endswith(".bin"):
                parts[int(name[len("kokoro-q8.part"):-4])] = tar.extractfile(member).read()
    onnx = b"".join(parts[i] for i in sorted(parts))
    if hashlib.sha256(onnx).hexdigest() != MODEL["sha256"]:
        raise RuntimeError("le modèle reconstitué ne correspond pas à l'empreinte attendue")
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(onnx)
    os.replace(tmp, path)  # écriture atomique : pas de modèle à moitié écrit en cache
    return path


def voice_path(name):
    """Fichier .bin du vecteur de voix : embarqué, en cache, ou extrait de kokoro-js."""
    bundled = os.path.join(SKILL_DIR, "assets", "voices", f"{name}.bin")
    if os.path.exists(bundled):
        return bundled
    cached = os.path.join(CACHE_DIR, "voices", f"{name}.bin")
    if os.path.exists(cached):
        return cached
    if os.path.exists(os.path.join(CACHE_DIR, "voices", ".complet")):  # déjà tout extrait : voix inexistante
        raise RuntimeError(f"voix Kokoro « {name} » introuvable (voir --list-voices)")
    data = _download(VOICES_PKG["tarball"], VOICES_PKG["integrity"])
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    found = False
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():  # met toutes les voix en cache d'un coup
            if member.isfile() and member.name.startswith("package/voices/") and member.name.endswith(".bin"):
                out = os.path.join(CACHE_DIR, "voices", os.path.basename(member.name))
                with open(out, "wb") as f:
                    f.write(tar.extractfile(member).read())
                found = found or os.path.basename(member.name) == f"{name}.bin"
    open(os.path.join(CACHE_DIR, "voices", ".complet"), "w").close()
    if not found:
        raise RuntimeError(f"voix Kokoro « {name} » introuvable (voir --list-voices)")
    return cached


_ENGINES = {}  # un moteur chargé par voix, réutilisé pour tous les segments d'un même texte


def pick_voice(lang_key, voice=None, gender="f"):
    _, female, male = LANGS[lang_key]
    return voice or (male if gender == "m" and male else female)


def load_style(voice):
    """Vecteur de style (510, 1, 256) d'une voix kokoro, dérivée ou non."""
    (np,) = deps.ensure("numpy")
    read = lambda path: np.fromfile(path, dtype=np.float32).reshape(-1, 256)  # noqa: E731
    if voice in DERIVED:
        style = read(voice_path("ff_siwis")).copy()
        timbre = DERIVED[voice][0]
        if timbre:
            direction = read(os.path.join(SKILL_DIR, "assets", "voices", "gender_direction.bin"))
            style[:, :128] += timbre * direction[:, :128]  # moitié timbre uniquement
    else:
        style = read(voice_path(voice))
    return style.reshape(-1, 1, 256).astype(np.float32)


def _engine(voice):
    if voice not in _ENGINES:
        kokoro_onnx, np = deps.ensure("kokoro_onnx", "numpy")
        style = load_style(voice)
        npz = os.path.join(CACHE_DIR, f"voice_{voice}.npz")
        if not os.path.exists(npz):
            os.makedirs(CACHE_DIR, exist_ok=True)
            np.savez(npz, **{voice: style})
        _ENGINES[voice] = kokoro_onnx.Kokoro(model_path(), npz)
    return _ENGINES[voice]


def synthesize(text, lang_key, voice=None, gender="f", speed=1.0):
    """Retourne (échantillons float32 mono, 24000, nom de la voix)."""
    (np,) = deps.ensure("numpy")
    voice = pick_voice(lang_key, voice, gender)
    samples, rate = _engine(voice).create(text, voice=voice, speed=speed, lang=LANGS[lang_key][0])
    samples = np.asarray(samples, dtype=np.float32)
    if voice in DERIVED:
        samples = _masculinize(samples, rate, *DERIVED[voice][1:])
    return samples, rate, voice


def _masculinize(samples, rate, formant_ratio, pitch_median):
    """« Change gender » de Praat : abaisse hauteur et formants, garde durées et forme de l'intonation."""
    parselmouth, np = deps.ensure("parselmouth", "numpy")
    from parselmouth.praat import call
    sound = parselmouth.Sound(samples.astype(np.float64), rate)
    # arguments : plancher et plafond de hauteur (Hz), rapport de formants, nouvelle hauteur médiane,
    # facteur d'étendue de hauteur (1 = intonation conservée), facteur de durée (1 = rythme conservé)
    out = call(sound, "Change gender", 75, 600, formant_ratio, pitch_median, 1.0, 1.0).values[0]
    peak = np.max(np.abs(out)) + 1e-9
    return (out / peak * min(1.0, np.max(np.abs(samples)) * 1.05)).astype(np.float32)
