#!/usr/bin/env python3
"""Texte -> voix (+ musique et bruitages) -> fichier audio (WAV, MP3, Opus) -> chaîne encodée.

Voix :
  - kokoro (défaut) : voix neuronale naturelle (Kokoro-82M). Français, anglais US/GB, espagnol,
    italien, portugais du Brésil, hindi. Poids (92 Mo) téléchargés et vérifiés au premier usage.
  - espeak : voix de synthèse robotique mais instantanée, plus de 100 langues.
  --engine auto (défaut) prend kokoro si possible, sinon espeak ; le résumé JSON dit lequel.

Mise en scène, directement dans le texte :
  [pause 0.8]           silence de 0,8 s
  [sfx pop]             bruitage à cet endroit (pop, clap, footsteps, swoosh… voir --list-sfx)
  [sfx footsteps 6]     nombre de pas ;  [sfx clap +0.2] décalage en secondes
  « … » ou « ... »      pause comique automatique (--ellipsis-pause, 0,6 s par défaut)
  {l'HEH|l'Ache E Ache} prononcer autrement : affiché à gauche (chronologie), dit à droite
Options : --music pizzicato|lofi|ambient|upbeat, --sfx nom@secondes, --stems, --intro/--outro.
Avec plusieurs segments, de la musique ou des bruitages, une chronologie <nom>.timeline.json est
écrite (début et fin de chaque phrase, instant de chaque bruitage) pour synchroniser une vidéo.

Les dépendances pip s'installent automatiquement au premier lancement.

Exemples :
  python3 tts_encode.py "Bonjour tout le monde" --out-dir out
  python3 tts_encode.py "Salut… [sfx pop] c'est moi." --music pizzicato --audio-format opus --out-dir out
  python3 tts_encode.py --text-file script.txt --music lofi --stems --out-dir out
"""
import argparse
import array
import ctypes
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deps  # noqa: E402
import kokoro_engine  # noqa: E402
import textcodecs  # noqa: E402

AUDIO_OUTPUT_SYNCHRONOUS = 2
ESPEAK_CHARS_UTF8 = 1
ESPEAK_RATE, ESPEAK_VOLUME, ESPEAK_PITCH = 1, 2, 3
ESPEAK_BASE_WPM = 160

QUALITY = {  # compression_level de libsndfile (0 = meilleure qualité, 1 = plus petit fichier)
    "mp3": {"haute": 0.5, "normale": 0.9, "compacte": 0.95},
    "opus": {"haute": 0.9, "normale": 0.95, "compacte": 1.0},
}
MIME = {"wav": "audio/wav", "mp3": "audio/mpeg", "opus": "audio/ogg"}
OPUS_RATES = (8000, 12000, 16000, 24000, 48000)
JOIN_GAP = 0.12  # petit silence entre deux segments coupés par un marqueur [sfx]


# ---------------------------------------------------------------- espeak-ng (secours)

class VoiceStruct(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p), ("languages", ctypes.c_char_p), ("identifier", ctypes.c_char_p),
        ("gender", ctypes.c_ubyte), ("age", ctypes.c_ubyte), ("variant", ctypes.c_ubyte),
        ("xx1", ctypes.c_ubyte), ("score", ctypes.c_int), ("spare", ctypes.c_void_p),
    ]


def load_espeak():
    (loader,) = deps.ensure("espeakng_loader")
    lib = ctypes.CDLL(loader.get_library_path())
    lib.espeak_Initialize.restype = ctypes.c_int
    rate = lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, loader.get_data_path().encode(), 0)
    if rate <= 0:
        sys.exit("Échec de l'initialisation d'espeak-ng.")
    return lib, rate


def espeak_voices(lib):
    lib.espeak_ListVoices.restype = ctypes.POINTER(ctypes.POINTER(VoiceStruct))
    voices = lib.espeak_ListVoices(None)
    out, i = set(), 0
    while voices[i]:
        v = voices[i].contents
        lang = (v.languages or b"")[1:].split(b"\0")[0].decode("utf-8", "replace")
        out.add((lang, v.name.decode("utf-8", "replace")))
        i += 1
    return sorted(out)


def espeak_synthesize(text, voice, speed, pitch, volume):
    """Retourne (échantillons float32 mono, fréquence)."""
    (np,) = deps.ensure("numpy")
    lib, rate = load_espeak()
    cb_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
    samples = array.array("h")

    @cb_type
    def on_audio(wav, n, _events):
        if wav and n > 0:
            samples.extend(wav[:n])
        return 0

    lib.espeak_SetSynthCallback(on_audio)
    if lib.espeak_SetVoiceByName(voice.encode()) != 0:
        sys.exit(f"Voix espeak « {voice} » inconnue. Liste : tts_encode.py --list-voices")
    lib.espeak_SetParameter(ESPEAK_RATE, int(round(ESPEAK_BASE_WPM * speed)), 0)
    lib.espeak_SetParameter(ESPEAK_PITCH, pitch, 0)
    lib.espeak_SetParameter(ESPEAK_VOLUME, volume, 0)
    raw = text.encode("utf-8")
    rc = lib.espeak_Synth(raw, len(raw) + 1, 0, 0, 0, ESPEAK_CHARS_UTF8, None, None)
    lib.espeak_Synchronize()
    lib.espeak_Terminate()
    if rc != 0 or not samples:
        sys.exit(f"La synthèse n'a produit aucun son pour « {text[:40]} ».")
    pcm = np.frombuffer(samples.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
    return pcm, rate


# ---------------------------------------------------------------- script : texte + marqueurs

MARKER = re.compile(r"\[\s*(pause|sfx)\b([^\]]*)\]", re.I)
ELLIPSIS = re.compile(r"(…|\.\.\.)\s+")
SAY_AS = re.compile(r"\{([^{}|]*)\|([^{}]*)\}")  # {texte affiché|texte prononcé}


def spoken(text):
    return SAY_AS.sub(lambda m: m.group(2), text)


def shown(text):
    return SAY_AS.sub(lambda m: m.group(1), text)


def parse_script(text, ellipsis_pause):
    """Découpe le texte en événements : ("text", str) / ("pause", s) / ("sfx", nom, nombre, décalage)."""
    events, pos = [], 0

    def add_text(chunk):
        if ellipsis_pause > 0:
            parts, last = [], 0
            for m in ELLIPSIS.finditer(chunk):
                parts.append(chunk[last:m.end(1)])
                last = m.end()
            parts.append(chunk[last:])
            for i, part in enumerate(parts):
                if part.strip():
                    events.append(("text", part.strip()))
                if i < len(parts) - 1:
                    events.append(("pause", ellipsis_pause))
        elif chunk.strip():
            events.append(("text", chunk.strip()))

    for m in MARKER.finditer(text):
        add_text(text[pos:m.start()])
        kind, args = m.group(1).lower(), m.group(2).split()
        if kind == "pause":
            try:
                events.append(("pause", float(args[0]) if args else 0.5))
            except ValueError:
                sys.exit(f"Marqueur invalide : {m.group(0)} (attendu : [pause 0.8])")
        else:
            if not args:
                sys.exit(f"Marqueur invalide : {m.group(0)} (attendu : [sfx pop])")
            name, count, offset = args[0].lower(), None, 0.0
            for a in args[1:]:
                if a[0] in "+-":
                    offset = float(a)
                elif a.isdigit():
                    count = int(a)
            events.append(("sfx", name, count, offset))
        pos = m.end()
    add_text(text[pos:])
    return events


def parse_abs_sfx(specs):
    """--sfx nom@secondes (nom peut être suivi de :N pour un nombre de pas)."""
    out = []
    for spec in specs or []:
        try:
            name, at = spec.split("@")
            name, _, count = name.partition(":")
            out.append((name.strip().lower(), int(count) if count else None, float(at)))
        except ValueError:
            sys.exit(f"--sfx invalide : « {spec} » (attendu : clap@4.2 ou footsteps:6@5)")
    return out


# ---------------------------------------------------------------- encodage audio

def render(pcm, rate, fmt, quality):
    """Retourne (octets du fichier audio, fréquence du fichier)."""
    sf, np = deps.ensure("soundfile", "numpy")
    pcm = np.clip(pcm, -1.0, 1.0).astype(np.float32)
    buf = io.BytesIO()
    buf.name = "audio." + fmt
    if fmt == "wav":
        sf.write(buf, pcm, rate, format="WAV", subtype="PCM_16")
        return buf.getvalue(), rate
    level = QUALITY[fmt][quality]
    if fmt == "mp3":
        sf.write(buf, pcm, rate, format="MP3", subtype="MPEG_LAYER_III",
                 compression_level=level, bitrate_mode="CONSTANT")
        # Étiquette ID3v1 finale (ignorée par les lecteurs) : marqueur de fin pour verify_roundtrip.py
        id3v1 = b"TAG" + b"tts-audio-base64".ljust(30, b"\0") + b"\0" * 94 + b"\xff"
        return buf.getvalue() + id3v1, rate
    out_rate = rate
    if rate not in OPUS_RATES:
        out_rate = 24000
        n_out = int(len(pcm) * out_rate / rate)
        pcm = np.interp(np.arange(n_out) * rate / out_rate, np.arange(len(pcm)), pcm).astype(np.float32)
    sf.write(buf, pcm, out_rate, format="OGG", subtype="OPUS", compression_level=level)
    return buf.getvalue(), out_rate


# ---------------------------------------------------------------- programme principal

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("text", nargs="?", help="Texte à prononcer, marqueurs compris (ou --text-file / stdin).")
    p.add_argument("--text-file", help="Fichier texte UTF-8 à lire.")
    p.add_argument("--lang", default="fr", help="fr (défaut), en-us, en-gb, es, it, pt-br, hi, ou langue espeak.")
    p.add_argument("--engine", choices=["auto", "kokoro", "espeak"], default="auto")
    p.add_argument("--gender", choices=["f", "m"], default="f",
                   help="Voix féminine (défaut) ou masculine (en français : voix dérivée fm_siwis).")
    p.add_argument("--voice", help="Nom exact d'une voix kokoro (ex. af_bella, fm_siwis_grave), prioritaire sur --gender.")
    p.add_argument("--variant", help="espeak uniquement : m1..m7, f1..f5, whisper…")
    p.add_argument("--speed", type=float, default=1.0, help="Vitesse relative (0.5 à 2.0). Défaut : 1.0.")
    p.add_argument("--pitch", type=int, default=50, help="espeak uniquement : hauteur 0-100.")
    p.add_argument("--volume", type=int, default=100, help="espeak uniquement : volume 0-200.")
    p.add_argument("--ellipsis-pause", type=float, default=0.6, help="Pause après « … » (s). 0 = aucune.")
    # bande-son
    p.add_argument("--music", choices=["none", "pizzicato", "lofi", "ambient", "upbeat"], default="none",
                   help="Musique de fond générée par code.")
    p.add_argument("--music-seed", type=int, default=0, help="Variante de mélodie (entier).")
    p.add_argument("--tempo", type=int, help="Tempo en bpm (défaut selon le thème).")
    p.add_argument("--music-level", type=float, default=-20.0,
                   help="Niveau de la musique sous la voix, en dB relatifs à la voix. Défaut : -20.")
    p.add_argument("--music-gap-level", type=float, default=-12.0,
                   help="Niveau de la musique hors parole (intro, pauses, fin). Défaut : -12.")
    p.add_argument("--sfx", action="append", metavar="NOM@SECONDES",
                   help="Bruitage à un instant absolu du fichier final (répétable), ex. clap@4.2.")
    p.add_argument("--sfx-level", type=float, default=-6.0, help="Crête des bruitages vs la voix (dB). Défaut : -6.")
    p.add_argument("--intro", type=float, help="Secondes avant la voix (défaut : 1.0 avec musique, sinon 0).")
    p.add_argument("--outro", type=float, help="Secondes après la voix (défaut : 2.0 avec musique, 0.5 avec bruitages).")
    p.add_argument("--stems", action="store_true",
                   help="Écrit aussi les pistes séparées voix / musique / bruitages (WAV), pour un montage vidéo.")
    # sortie
    p.add_argument("--audio-format", choices=["wav", "mp3", "opus"], default="wav")
    p.add_argument("--quality", choices=["haute", "normale", "compacte"], default="normale")
    p.add_argument("--encoding", choices=list(textcodecs.EXTENSIONS), default="base64")
    p.add_argument("--wrap", type=int, default=0, help="Coupe la chaîne en lignes de N caractères.")
    p.add_argument("--data-uri", action="store_true", help="Écrit aussi un data URI (base64) pour <audio src>.")
    p.add_argument("--out-dir", default=".")
    p.add_argument("--name", default="audio")
    p.add_argument("--print", dest="print_encoded", action="store_true")
    p.add_argument("--list-voices", action="store_true", help="Liste les voix kokoro et espeak, puis quitte.")
    p.add_argument("--list-sfx", action="store_true", help="Liste les bruitages et thèmes musicaux, puis quitte.")
    args = p.parse_args()

    if args.list_sfx:
        import soundtrack
        print("# bruitages ([sfx nom] dans le texte, ou --sfx nom@secondes)")
        for n in soundtrack.SFX_NAMES:
            print(f"{n}\t{soundtrack.SFX_HELP[n]}")
        print("# thèmes musicaux (--music)")
        print(soundtrack.__doc__.split("Thèmes musicaux (MUSIC_STYLES) :")[1].split("Bruitages")[0].rstrip())
        return
    if args.list_voices:
        print("# kokoro (voix neuronales) : langue -> voix féminine / masculine")
        for key, (_, female, male) in kokoro_engine.LANGS.items():
            print(f"{key}\t{female} / {male or '—'}")
        print("# voix masculines françaises dérivées (--voice) : "
              + ", ".join(f"{n} (≈{v[2]} Hz)" for n, v in kokoro_engine.DERIVED.items()))
        print("# espeak (voix de synthèse) : langue, nom")
        lib, _ = load_espeak()
        for lang, name in espeak_voices(lib):
            print(f"{lang}\t{name}")
        return

    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read()
    elif args.text is not None:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        p.error("Aucun texte fourni (argument, --text-file ou stdin).")
    if not 0.5 <= args.speed <= 2.0:
        p.error("--speed doit être entre 0.5 et 2.0.")

    events = parse_script(text.strip(), args.ellipsis_pause)
    abs_sfx = parse_abs_sfx(args.sfx)
    if not any(e[0] == "text" for e in events):
        p.error("Le texte est vide (seulement des marqueurs ?).")
    use_soundtrack = args.music != "none" or abs_sfx or any(e[0] == "sfx" for e in events)
    if use_soundtrack:
        import soundtrack
        for name in [e[1] for e in events if e[0] == "sfx"] + [s[0] for s in abs_sfx]:
            if name not in soundtrack.SFX_NAMES:
                p.error(f"bruitage inconnu « {name} » ({', '.join(soundtrack.SFX_NAMES)})")

    # ---- choix du moteur
    notes = []
    lang_key = kokoro_engine.resolve_lang(args.lang)
    engine = args.engine
    if engine == "kokoro" and lang_key is None:
        p.error(f"kokoro ne gère pas la langue « {args.lang} » ({', '.join(kokoro_engine.LANGS)}). "
                "Utiliser --engine espeak.")
    if engine == "auto":
        engine = "kokoro" if lang_key else "espeak"
        if not lang_key:
            notes.append(f"langue « {args.lang} » non gérée par la voix neuronale : voix espeak utilisée")
    if engine == "kokoro" and args.gender == "m" and not args.voice and kokoro_engine.LANGS[lang_key][2] is None:
        notes.append(f"pas de voix masculine kokoro en « {lang_key} » : voix féminine utilisée")

    (np,) = deps.ensure("numpy")
    state = {"engine": engine, "voice": None}

    def speak(segment):
        if state["engine"] == "kokoro":
            try:
                pcm, rate, state["voice"] = kokoro_engine.synthesize(segment, lang_key, args.voice, args.gender, args.speed)
                return pcm, rate
            except Exception as exc:  # réseau bloqué, voix inconnue…
                if args.engine == "kokoro":
                    sys.exit(f"Voix neuronale indisponible : {exc}")
                notes.append(f"voix neuronale indisponible ({exc}) : voix espeak utilisée à la place")
                state["engine"] = "espeak"
        espeak_lang = "fr" if lang_key == "fr" else args.lang
        state["voice"] = espeak_lang + (f"+{args.variant}" if args.variant else ("+m3" if args.gender == "m" else ""))
        return espeak_synthesize(segment, state["voice"], args.speed, args.pitch, args.volume)

    # ---- voix, segment par segment, avec la chronologie
    pieces, timeline_segments, sfx_events = [], [], []
    rate, cursor, prev = None, 0.0, None
    for ev in events:
        if ev[0] == "text":
            pcm, r = speak(spoken(ev[1]))
            if rate is None:
                rate = r
            elif r != rate:  # repli espeak en cours de route : on aligne la fréquence
                pcm = np.interp(np.arange(int(len(pcm) * rate / r)) * r / rate, np.arange(len(pcm)), pcm)
            if prev == "text_or_sfx":
                pieces.append(JOIN_GAP)
                cursor += JOIN_GAP
            pieces.append(pcm.astype(np.float32))
            timeline_segments.append({"text": shown(ev[1]), "start": cursor, "end": cursor + len(pcm) / rate})
            cursor += len(pcm) / rate
            prev = "text"
        elif ev[0] == "pause":
            pieces.append(ev[1])  # silence en secondes, converti une fois la fréquence connue
            cursor += ev[1]
            prev = "pause"
        else:
            sfx_events.append({"name": ev[1], "count": ev[2], "time": max(0.0, cursor + ev[3]), "anchor": "texte"})
            prev = "text_or_sfx" if prev == "text" else prev
    voice_pcm = np.concatenate([np.zeros(int(round(x * rate)), np.float32) if isinstance(x, float) else x
                                for x in pieces])
    voice_dur = len(voice_pcm) / rate

    # ---- bande-son : musique + bruitages + mixage voix d'abord
    timeline = None
    stems = {}
    if use_soundtrack:
        import soundtrack
        intro = args.intro if args.intro is not None else (1.0 if args.music != "none" else 0.0)
        outro = args.outro if args.outro is not None else (2.0 if args.music != "none" else 0.5)
        for e in sfx_events:
            e["time"] += intro
        for name, count, at in abs_sfx:
            sfx_events.append({"name": name, "count": count, "time": at, "anchor": "absolu"})
        sfx_sounds = {id(e): soundtrack.sfx(e["name"], args.music_seed, e["count"]) for e in sfx_events}
        end_sfx = max([e["time"] + len(sfx_sounds[id(e)]) / soundtrack.SR for e in sfx_events], default=0)
        total = max(intro + voice_dur + outro, end_sfx + 0.1)
        n = int(total * soundtrack.SR)
        voice48 = np.zeros(n)
        v = soundtrack.resample(voice_pcm, rate)
        voice48[int(intro * soundtrack.SR):int(intro * soundtrack.SR) + len(v)] = v[:n - int(intro * soundtrack.SR)]
        music = soundtrack.music(args.music, total, args.music_seed, args.tempo) if args.music != "none" else None
        sfx_track = np.zeros(n)
        for e in sfx_events:
            soundtrack._place(sfx_track, sfx_sounds[id(e)], e["time"])
        pcm_out, stems = soundtrack.mix(voice48, music, sfx_track if sfx_events else None,
                                        args.music_level, args.music_gap_level, args.sfx_level)
        out_rate = soundtrack.SR
        for s in timeline_segments:
            s["start"] += intro
            s["end"] += intro
    else:
        intro, pcm_out, out_rate = 0.0, voice_pcm, rate

    if len(timeline_segments) > 1 or use_soundtrack:
        timeline = {
            "duration_s": round(len(pcm_out) / out_rate, 3),
            "voice_start_s": round(timeline_segments[0]["start"], 3),
            "voice_end_s": round(timeline_segments[-1]["end"], 3),
            "music": None if args.music == "none" else {"style": args.music, "seed": args.music_seed},
            "segments": [{"text": s["text"], "start_s": round(s["start"], 3), "end_s": round(s["end"], 3)}
                         for s in timeline_segments],
            "sfx": [{"name": e["name"], "time_s": round(e["time"], 3), "placed_by": e["anchor"]}
                    for e in sorted(sfx_events, key=lambda e: e["time"])],
        }

    audio, file_rate = render(pcm_out, out_rate, args.audio_format, args.quality)

    # ---- écriture des fichiers
    os.makedirs(args.out_dir, exist_ok=True)
    base = os.path.join(args.out_dir, args.name)
    audio_path = f"{base}.{args.audio_format}"
    with open(audio_path, "wb") as f:
        f.write(audio)
    encoded = textcodecs.encode(audio, args.encoding)
    if args.wrap > 0:
        encoded = "\n".join(encoded[i:i + args.wrap] for i in range(0, len(encoded), args.wrap))
    enc_path = f"{base}.{args.audio_format}.{textcodecs.EXTENSIONS[args.encoding]}.txt"
    with open(enc_path, "w", encoding="ascii") as f:
        f.write(encoded + "\n")

    summary = {
        "engine": state["engine"],
        "voice": state["voice"],
        "audio_file": audio_path,
        "audio_format": args.audio_format,
        "quality": args.quality if args.audio_format != "wav" else None,
        "encoded_file": enc_path,
        "encoding": args.encoding,
        "sample_rate_hz": file_rate,
        "duration_s": round(len(pcm_out) / out_rate, 2),
        "audio_bytes": len(audio),
        "encoded_chars": len(encoded.replace("\n", "")),
        "audio_sha256": hashlib.sha256(audio).hexdigest(),
    }
    if timeline:
        tl_path = f"{base}.timeline.json"
        with open(tl_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, ensure_ascii=False, indent=2)
        summary["timeline_file"] = tl_path
        summary["segments"] = len(timeline_segments)
        summary["sfx"] = [f"{e['name']}@{e['time_s']}" for e in timeline["sfx"]]
        summary["music"] = args.music if args.music != "none" else None
    if args.stems and stems:
        sf, = deps.ensure("soundfile")
        summary["stems"] = {}
        for k, sig in stems.items():
            path = f"{base}.{k}.wav"
            sf.write(path, np.clip(sig, -1, 1).astype(np.float32), out_rate, subtype="PCM_16")
            summary["stems"][k] = path
    elif args.stems:
        notes.append("--stems ignoré : pas de musique ni de bruitage, l'audio principal est déjà la voix seule")
    if args.data_uri:
        uri_path = f"{base}.{args.audio_format}.datauri.txt"
        with open(uri_path, "w", encoding="ascii") as f:
            f.write(f"data:{MIME[args.audio_format]};base64," + textcodecs.encode(audio, "base64") + "\n")
        summary["data_uri_file"] = uri_path
    if notes:
        summary["notes"] = list(dict.fromkeys(notes))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.print_encoded:
        print(encoded)


if __name__ == "__main__":
    main()
