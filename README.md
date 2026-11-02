# tts-audio-base64

Un skill pour Claude qui transforme un texte en **voix naturelle**, ajoute si besoin une **musique de fond** et des **bruitages**, et livre le son en fichier **WAV, MP3 ou Opus**, ou encodé en texte (**base64, base32, base85, basE91**, ou data URI prêt pour une balise `<audio>`).

Pensé pour les voix off de vidéos : il fournit aussi une **chronologie JSON** (début et fin de chaque phrase, instant de chaque bruitage) et les **pistes séparées** voix / musique / bruitages pour le montage.

## Fonctionnalités

- **Voix neuronale Kokoro-82M**, en français, anglais (US et GB), espagnol, italien, portugais du Brésil et hindi, avec une voix féminine et une voix masculine par langue. Plus de 100 autres langues avec la voix de secours espeak-ng, robotique.
- **Voix masculine française sans accent**, dérivée de la voix française d'origine (voir [Comment ça marche](#comment-ça-marche)).
- **Mise en scène dans le texte** : pauses, bruitages, pause comique automatique sur « … », prononciation corrigée des sigles et mots étrangers.
- **Musique générée par code** (4 thèmes) et **9 bruitages**, mixés « voix d'abord » : la musique baisse automatiquement sous la voix.
- **Vérification de chaque chaîne encodée** : décodage complet, contrôle de structure, détection des fichiers tronqués ou altérés.
- **Aucune installation manuelle** : les dépendances s'installent via pip au premier lancement, le modèle (92 Mo) est téléchargé depuis npm et vérifié par empreinte SHA-256.

## Installation

Télécharge `tts-audio-base64.skill` depuis la page [Releases](../../releases) et ajoute-le à tes skills dans Claude. Ensuite, il suffit de demander, par exemple :

> Fais-moi une voix off masculine qui dit « Le réseau est en panne… encore. Bon, on redémarre le routeur. », avec une petite musique lo-fi derrière, un ding après « encore », et donne-moi la chronologie pour ma vidéo.

> J'ai besoin d'un audio en base64 de « Accès autorisé, bonne journée », le plus léger possible pour une balise audio.

## Utilisation en ligne de commande

Les scripts fonctionnent aussi seuls, avec Python 3.10 ou plus récent :

```bash
# Phrase simple, WAV + chaîne base64
python3 scripts/tts_encode.py "Bonjour tout le monde" --out-dir sortie

# Voix masculine, Opus compact, encodage base85
python3 scripts/tts_encode.py "Alerte : intrusion détectée" --gender m \
  --audio-format opus --quality compacte --encoding base85 --out-dir sortie

# Voix off complète depuis un fichier, avec musique, bruitages et pistes séparées
python3 scripts/tts_encode.py --text-file script.txt --gender m --music pizzicato \
  --stems --audio-format mp3 --out-dir sortie --name voixoff

# Vérifier une chaîne, ou la décoder en fichier audio
python3 scripts/verify_roundtrip.py sortie/voixoff.mp3.b64.txt --encoding base64 --original sortie/voixoff.mp3
python3 scripts/verify_roundtrip.py chaine.txt --encoding base64 --decode-to son.mp3

# Lister les voix, les bruitages et les thèmes musicaux
python3 scripts/tts_encode.py --list-voices
python3 scripts/tts_encode.py --list-sfx
```

### Marqueurs dans le texte

| Marqueur | Effet |
|---|---|
| `[pause 0.8]` | silence de 0,8 s |
| `…` ou `...` suivi d'un espace | pause comique automatique (0,6 s) |
| `[sfx pop]` | bruitage à cet endroit |
| `[sfx footsteps 6]`, `[sfx clap +0.2]` | nombre de pas, décalage en secondes |
| `{l'HEH\|l'Ache E Ache}` | affiche la partie gauche, prononce la partie droite |

Exemple de `script.txt` :

```
[sfx shimmer] [pause 0.9] Stop réviser à la bibliothèque. [pause 0.3] Fais-y la fête. [sfx pop] [pause 0.4]
Les amis de {l'HEH|l'Ache E Ache}… et les inconnus aussi, bon. [sfx clap] [pause 0.5]
Hier, j'ai maté {Project X|Prodjèkt ex}. [sfx footsteps 4] [pause 1.1] [sfx swoosh]
```

**Thèmes musicaux** : `pizzicato`, `lofi`, `ambient`, `upbeat`.
**Bruitages** : `shimmer`, `pop`, `clap`, `thud`, `footsteps`, `swoosh`, `whoosh`, `ding`, `click`.

### Voix françaises

| Voix | Hauteur | Remarque |
|---|---|---|
| `ff_siwis` | ≈ 205 Hz | voix féminine d'origine (par défaut) |
| `fm_siwis_leger` | ≈ 140 Hz | masculine, jeune et claire |
| `fm_siwis` | ≈ 120 Hz | masculine (défaut de `--gender m`) |
| `fm_siwis_grave` | ≈ 108 Hz | masculine, grave |
| `fm_siwis_timbre` | ≈ 120 Hz | timbre plus masculin issu du modèle |

### Taille des chaînes

Pour une phrase de 5,6 secondes, en nombre de caractères :

| Format | base64 | base85 | basE91 |
|---|---|---|---|
| WAV | 359 144 | 336 695 | 330 110 |
| MP3 (normale) | 22 828 | 21 400 | 21 026 |
| Opus (normale) | 18 764 | 17 592 | 17 229 |
| Opus (compacte, 8 kbit/s) | 7 120 | 6 674 | 6 485 |

C'est le format audio qui réduit la taille, bien plus que l'encodage. Le base64 est le seul que les navigateurs décodent nativement. Le base85 est sûr dans du JSON (ni `"` ni `\`).

## Comment ça marche

- **Synthèse** : [Kokoro-82M](https://github.com/hexgrad/kokoro) via `kokoro-onnx` et onnxruntime, sur processeur. Compter environ une seconde de calcul par seconde d'audio.
- **Voix masculine française** : Kokoro n'a qu'une voix française, féminine. Le skill synthétise avec elle, puis applique la fonction « Change gender » de [Praat](https://www.fon.hum.uva.nl/praat/) (via `praat-parselmouth`) : hauteur et formants abaissés, rythme et intonation conservés. Comme la prosodie reste celle de la voix française, il n'y a pas d'accent étranger. Déplacer tout le vecteur de style vers des voix d'homme d'autres langues produisait un accent : rythme modifié de 5,6 %, intonation corrélée à 0,84 seulement.
- **Musique et bruitages** : synthétisés en numpy (cordes pincées additives, piano électrique en FM, nappes, batterie lo-fi), puis mixés avec atténuation de la musique pendant la parole.
- **Encodages** : base64, base32 et base85 via la bibliothèque standard Python ; basE91 implémenté en Python pur (`scripts/textcodecs.py`).

## Structure

```
SKILL.md                 instructions lues par Claude
scripts/
  tts_encode.py          texte → voix (+ bande-son) → fichier audio → chaîne encodée
  verify_roundtrip.py    vérification et décodage d'une chaîne
  kokoro_engine.py       voix neuronale, téléchargement vérifié du modèle
  soundtrack.py          musique, bruitages, mixage
  textcodecs.py          base64 / base32 / base85 / basE91
  deps.py                installation des dépendances à la demande
assets/voices/           voix française, direction masculine, licences
evals/                   cas de test (format claude plugin eval)
```

## Tests

Le dossier `evals/` contient 6 cas de test : phrase en base64, base32 avec retours à la ligne, décodage d'une chaîne reçue, data URI MP3, chaîne JSON compacte, et voix off avec musique et bruitages. Avec Claude Code :

```bash
claude plugin eval . --allow-tools Write,Edit,Bash --scaffold
```

## Limites

- La voix reste synthétique : pas d'accent régional, pas d'émotion contrôlable (sourire, ton complice), pas de respirations.
- La voix masculine française est une transformation du signal ; elle peut sonner un peu « traitée ».
- La musique générée par code est simple, loin d'une vraie bande-son.
- Le premier lancement télécharge une centaine de Mo (paquets pip et modèle) depuis PyPI et npm, plus 26 Mo pour les voix des autres langues que le français.

## Licence et crédits

Ce projet est distribué sous licence **GPL-3.0** (voir [LICENSE](LICENSE)).

- **Kokoro-82M** et ses voix, par hexgrad, sous Apache 2.0. La voix `ff_siwis` (corpus SIWIS) et la direction masculine qui en dérive sont incluses dans `assets/voices/` avec leur licence et leur notice ([NOTICE.md](assets/voices/NOTICE.md)).
- **Praat** (Paul Boersma et David Weenink) via **parselmouth** (Yannick Jadoul), sous GPL-3.0, installé par pip et non redistribué ici.
- **espeak-ng** via `espeakng-loader`, sous GPL-3.0.
- **libsndfile** via `soundfile` pour l'écriture et la lecture MP3, Opus et WAV.
