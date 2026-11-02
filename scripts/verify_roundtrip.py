#!/usr/bin/env python3
"""Vérifie qu'une chaîne encodée (base64/32/85/91) se décode en un fichier audio valide et complet.

Usage :
  python3 verify_roundtrip.py ENCODED_FILE --encoding base64|base32|base85|base91
                              [--original FICHIER] [--decode-to OUT]

Contrôles :
  - la chaîne se décode (alphabet et padding corrects) ;
  - le format est reconnu d'après les premiers octets (RIFF = WAV, OggS = Opus, ID3/trame MPEG = MP3) ;
  - la structure est complète (en-tête RIFF du WAV, page de fin du flux Ogg, trames MP3 entières),
    ce qui détecte une chaîne tronquée ; puis l'audio est réellement décodé (soundfile) ;
  - si --original est donné (--wav est un alias), les octets sont identiques à ce fichier.
Code de sortie 0 si tout est bon, 1 sinon. Sert aussi à décoder une chaîne reçue : --decode-to.
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deps  # noqa: E402
import textcodecs  # noqa: E402


def detect_format(data):
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"OggS":
        return "opus"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


# --- Contrôles de structure : détectent une chaîne tronquée, que libsndfile accepterait en silence ---

_MP3_BITRATES = {  # kbit/s, couche III
    "v1": [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    "v2": [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _check_wav(data):
    import wave
    with wave.open(io.BytesIO(data), "rb") as w:
        declared = w.getnframes()
        real = len(w.readframes(declared)) // (w.getsampwidth() * w.getnchannels())
    if real < declared:
        return f"fichier tronqué : {real} trames présentes sur {declared} annoncées dans l'en-tête RIFF"
    return None


def _check_ogg(data):
    """Parcourt les pages Ogg : chaque page doit être complète et la dernière marquée fin de flux."""
    pos, last_flags = 0, None
    while pos < len(data):
        if data[pos:pos + 4] != b"OggS" or pos + 27 > len(data):
            return "flux Ogg abîmé ou tronqué (en-tête de page incomplet)"
        n_seg = data[pos + 26]
        if pos + 27 + n_seg > len(data):
            return "flux Ogg tronqué (table de segments incomplète)"
        body = sum(data[pos + 27:pos + 27 + n_seg])
        end = pos + 27 + n_seg + body
        if end > len(data):
            return "flux Ogg tronqué (dernière page incomplète)"
        last_flags, pos = data[pos + 5], end
    if last_flags is None or not last_flags & 0x04:
        return "flux Ogg tronqué (pas de page de fin de flux)"
    return None


def _check_mp3(data):
    """Parcourt les trames MP3 (couche III) : la dernière doit se terminer exactement en fin de données.

    Retourne (erreur ou None, marqueur_de_fin_présent). Sans étiquette ID3v1 finale, une coupure
    tombant pile entre deux trames reste indétectable : l'appelant le signale.
    """
    has_end_tag = len(data) >= 128 and data[-128:-125] == b"TAG"
    end = len(data) - 128 if has_end_tag else len(data)
    err = _walk_mp3(data[:end])
    return err, has_end_tag


def _walk_mp3(data):
    pos = 0
    if data[:3] == b"ID3":
        pos = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    frames = 0
    while pos + 4 <= len(data):
        b1, b2 = data[pos + 1], data[pos + 2]
        if data[pos] != 0xFF or (b1 & 0xE0) != 0xE0:
            return "données MP3 abîmées ou tronquées (en-tête de trame introuvable)"
        version, layer = (b1 >> 3) & 3, (b1 >> 1) & 3
        if layer != 1 or version == 1:
            return None  # pas de la couche III : on laisse soundfile juger
        br = _MP3_BITRATES["v1" if version == 3 else "v2"][b2 >> 4] if (b2 >> 4) < 15 else 0
        sr_idx = (b2 >> 2) & 3
        if not br or sr_idx == 3:
            return "données MP3 abîmées (en-tête de trame invalide)"
        rate = _MP3_RATES[version][sr_idx]
        length = (144 if version == 3 else 72) * br * 1000 // rate + ((b2 >> 1) & 1)
        if pos + length > len(data):
            return f"fichier MP3 tronqué (trame n° {frames + 1} incomplète)"
        pos += length
        frames += 1
    if pos != len(data):
        return "fichier MP3 tronqué (fin de trame incomplète)"
    return None


def structural_check(fmt, data):
    """Retourne (erreur ou None, avertissement ou None)."""
    try:
        if fmt == "mp3":
            err, has_end_tag = _check_mp3(data)
            warn = None if has_end_tag else (
                "MP3 sans marqueur de fin : une coupure tombant pile entre deux trames ne serait pas détectée ; "
                "comparer à l'original (--original) si possible")
            return err, (None if err else warn)
        return {"wav": _check_wav, "opus": _check_ogg}[fmt](data), None
    except Exception as exc:  # en-tête illisible
        return f"structure {fmt} illisible : {exc}", None


def fail(report, message):
    report["error"] = message
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("encoded_file")
    p.add_argument("--encoding", choices=list(textcodecs.EXTENSIONS), required=True)
    p.add_argument("--original", "--wav", dest="original", help="Fichier audio original à comparer.")
    p.add_argument("--decode-to", help="Écrit le fichier audio décodé à ce chemin.")
    args = p.parse_args()

    with open(args.encoded_file, encoding="ascii") as f:
        raw = f.read().strip()
    if raw.startswith("data:"):  # tolère un data URI
        raw = raw.split(",", 1)[1]

    report = {"ok": False}
    try:
        data = textcodecs.decode(raw, args.encoding)
    except ValueError as exc:  # binascii.Error hérite de ValueError
        fail(report, f"décodage {args.encoding} impossible : {exc}")

    fmt = detect_format(data)
    if fmt is None:
        fail(report, "format audio non reconnu (ni WAV, ni MP3, ni Opus) — mauvais encodage choisi ?")
    report["format"] = fmt

    problem, warning = structural_check(fmt, data)
    if problem:
        fail(report, problem)
    if warning:
        report["warning"] = warning

    (sf,) = deps.ensure("soundfile")
    buf = io.BytesIO(data)
    buf.name = "audio." + fmt
    try:
        with sf.SoundFile(buf) as snd:
            declared, rate, channels = snd.frames, snd.samplerate, snd.channels
            decoded = len(snd.read(dtype="int16"))
    except Exception as exc:  # libsndfile lève des erreurs variées sur un fichier abîmé
        fail(report, f"le résultat n'est pas un fichier {fmt} lisible : {exc}")
    if decoded == 0:
        fail(report, "aucun son décodé")
    if declared > 0 and decoded < 0.9 * declared:
        fail(report, f"fichier tronqué : {decoded / rate:.2f} s décodées sur {declared / rate:.2f} s annoncées")
    report.update(channels=channels, sample_rate_hz=rate, duration_s=round(decoded / rate, 2))

    if args.original:
        with open(args.original, "rb") as f:
            same = f.read() == data
        report["identical_to_original"] = same
        if not same:
            fail(report, "le fichier décodé diffère de l'original")

    if args.decode_to:
        with open(args.decode_to, "wb") as f:
            f.write(data)
        report["decoded_to"] = args.decode_to

    report["ok"] = True
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
