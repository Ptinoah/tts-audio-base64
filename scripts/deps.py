"""Installe à la demande les dépendances pip du skill, pour qu'il marche sans préparation.

Tout passe par pip (aucun paquet système, pas de ffmpeg) :
  - kokoro-onnx     : voix neuronale Kokoro (tire onnxruntime, phonemizer, espeakng-loader) ;
  - espeakng-loader : moteur espeak-ng, bibliothèque et données incluses (voix de secours) ;
  - soundfile       : libsndfile embarquée, lit/écrit WAV, MP3 et Opus (tire numpy et cffi).
"""
import importlib
import subprocess
import sys

PACKAGES = {
    "espeakng_loader": "espeakng-loader",
    "soundfile": "soundfile",
    "numpy": "numpy",
    # voix neuronale ; tire onnxruntime et phonemizer. Version bornée : l'API de create() est utilisée telle quelle.
    "kokoro_onnx": "kokoro-onnx>=0.6,<0.7",
    # Praat (via parselmouth) : sert à rendre masculine la voix française (voix fm_siwis*)
    "parselmouth": "praat-parselmouth",
}


def ensure(*modules):
    """Importe les modules demandés en installant ceux qui manquent. Retourne la liste des modules."""
    missing = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(PACKAGES.get(mod, mod))
    if missing:
        print(f"Installation des dépendances : {' '.join(missing)}…", file=sys.stderr)
        base = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *missing]
        ok = subprocess.run(base, capture_output=True).returncode == 0
        if not ok:  # environnements « externally managed » (Debian, conteneurs)
            ok = subprocess.run(base + ["--break-system-packages"], capture_output=True).returncode == 0
        if not ok:
            ok = subprocess.run(base + ["--user"], capture_output=True).returncode == 0
        importlib.invalidate_caches()
        if not ok:
            sys.exit(
                "Impossible d'installer automatiquement les dépendances. Lance à la main :\n"
                f"  {sys.executable} -m pip install {' '.join(missing)}"
            )
    return [importlib.import_module(m) for m in modules]
