---
name: tts-audio-base64
description: Génère une voix naturelle (synthèse vocale neuronale / text-to-speech) à partir d'un texte, avec si besoin musique de fond, bruitages et pauses, en fichier audio WAV, MP3 ou Opus, encodé en texte — base64, base32, base85 ou basE91 (« code64 », « code32 »…) — ou en data URI ; fournit aussi une chronologie et des pistes séparées pour un montage vidéo. À utiliser dès que l'utilisateur veut transformer du texte en voix, une voix off ou narration pour une vidéo, "faire parler" une phrase, une voix avec musique ou bruitages, un message audio sous forme de chaîne encodée, un data:audio, ou décoder/vérifier une telle chaîne — même s'il dit seulement « code64 », « code32 », « base85 », « voiceover », « audio en texte » ou « voix encodée ».
---

# Texte → voix → audio encodé en texte

Ce skill transforme un texte en parole, produit un fichier audio, puis l'encode en texte. L'utilisateur dit parfois « code64 » ou « code32 » : cela signifie base64 / base32.

## Les deux voix

- **kokoro** (par défaut) : voix neuronale Kokoro-82M, naturelle et intelligible. Langues : français (`fr`), anglais US (`en-us`) et britannique (`en-gb`), espagnol (`es`), italien (`it`), portugais du Brésil (`pt-br`), hindi (`hi`), chacune avec une voix féminine et une masculine (`--gender f|m`).
  - En français, la voix féminine `ff_siwis` est la voix d'origine (par défaut). La voix masculine `fm_siwis` en est dérivée sans accent (voir ci-dessous). Variantes : `fm_siwis_leger` (≈ 140 Hz, jeune homme à la voix claire), `fm_siwis` (≈ 120 Hz, défaut de `--gender m`), `fm_siwis_grave` (≈ 108 Hz), et `fm_siwis_timbre` (≈ 120 Hz, timbre plus masculin issu du modèle, intonation française à 97 %). Choisir d'après la description : « jeune », « voix claire », « medium pitch » → `fm_siwis_leger` ou `fm_siwis` ; « grave », « posé », « voix profonde » → `fm_siwis_grave`.
- **espeak** : voix de synthèse robotique, difficile à comprendre sur des phrases longues, mais instantanée et disponible dans plus de 100 langues. Elle sert de secours.

Avec `--engine auto` (défaut), le script prend kokoro si la langue est gérée, sinon espeak. Si le modèle kokoro est inaccessible, il bascule aussi sur espeak. Dans les deux cas, le résumé JSON l'indique dans `engine` et `notes` : **toujours prévenir l'utilisateur** quand `engine` vaut `espeak` alors qu'il n'a pas demandé cette voix, car le résultat sera bien moins compréhensible.

## Aucune préparation

Tout s'installe et se télécharge automatiquement au premier lancement, depuis PyPI et le registre npm uniquement (joignables partout où pip et npm le sont) :
- paquets pip (`deps.py`) : `kokoro-onnx` (avec onnxruntime), `espeakng-loader`, `soundfile`, et `praat-parselmouth` pour la voix masculine française ;
- poids du modèle kokoro, 92 Mo, depuis le paquet npm `kokoro-q8-shards`, vérifiés par empreinte SHA-256 ;
- voix kokoro autres que le français (26 Mo, une seule fois), depuis le paquet npm `kokoro-js`, vérifiées par empreinte npm. La voix française est embarquée dans `assets/voices/`.

Le cache est dans `~/.cache/tts-audio-base64` (ou `TTS_AUDIO_CACHE`). Compter ~15 s au premier lancement, puis environ une seconde de calcul par seconde d'audio. Pour un long texte, prévenir que ça prend un moment.

## Procédure

1. **Préparer le texte** pour qu'il se prononce bien. Les sigles sont lus comme des mots (« VLAN » → « vlan », « l'HEH » → « l'è ») et les mots anglais à la française (« Project X » → « projecte ixe ») : utiliser `{affiché|prononcé}`, par exemple `{VLAN|V-LAN}`, `{l'HEH|l'Ache E Ache}`, `{Project X|Prodjèkt ex}`. Éviter les graphies avec une lettre isolée suivie d'un tiret (« l'H-E-H ») : le moteur bascule en anglais. Ne pas changer le sens du texte demandé.
2. **Choisir les paramètres** à partir de la demande :
   - langue : `--lang fr` (défaut), `en-us`, `en-gb`, `es`, `it`, `pt-br`, `hi`, ou toute langue espeak (`--list-voices`) ;
   - voix : `--gender f|m`, ou `--voice af_bella` pour une voix kokoro précise ; `--speed 0.5` à `2.0` ;
   - format : `--audio-format wav` (défaut), `mp3` ou `opus`, et `--quality haute|normale|compacte` ;
   - encodage : `--encoding base64` (défaut), `base32`, `base85` ou `base91` ;
   - `--wrap N` pour couper la chaîne en lignes, `--data-uri` pour une balise `<audio>` ;
   - pauses, musique, bruitages : voir « Mise en scène » ci-dessous.
3. **Générer** :
   ```bash
   python3 <skill>/scripts/tts_encode.py "Texte à dire" --audio-format opus --encoding base64 --out-dir <dossier> --name message
   ```
   Pour un long texte ou un texte avec marqueurs : `--text-file texte.txt` (évite les soucis de guillemets dans le shell).
4. **Vérifier** avant de livrer — une chaîne abîmée ne se voit pas à l'œil :
   ```bash
   python3 <skill>/scripts/verify_roundtrip.py <dossier>/message.opus.b64.txt --encoding base64 --original <dossier>/message.opus
   ```
5. **Livrer** les fichiers (`SendUserFile`) : l'audio pour l'écoute, et le `.txt` pour la chaîne. Signaler le moteur utilisé s'il y a eu repli sur espeak.

## Mise en scène : pauses, musique, bruitages

Le texte peut contenir des marqueurs (le reste est dit tel quel) :

| Dans le texte | Effet |
|---|---|
| `[pause 0.8]` | silence de 0,8 s |
| `…` ou `...` suivi d'un espace | pause comique automatique de 0,6 s (`--ellipsis-pause`, 0 pour désactiver) |
| `[sfx pop]` | bruitage à cet endroit, à la fin de ce qui précède ; entre deux morceaux de phrase, il tombe dans le court silence (0,12 s) juste avant la suite, sans décalage à ajouter |
| `[sfx footsteps 6]` / `[sfx clap +0.2]` | nombre de pas / décalage en secondes (négatif : plus tôt) |
| `{l'HEH\|l'Ache E Ache}` | dit la partie droite, affiche la partie gauche dans la chronologie |

Options : `--music pizzicato|lofi|ambient|upbeat` (thèmes générés par code ; `--music-seed N` change la mélodie, `--tempo` le bpm), `--sfx clap@4.2` (bruitage à un instant absolu du fichier final, répétable), `--intro` / `--outro` (musique seule avant/après la voix ; 1 s et 2 s par défaut avec musique), `--stems` (pistes séparées), `--music-level`, `--music-gap-level`, `--sfx-level` (dB).

Bruitages disponibles (`--list-sfx`) : `shimmer` (scintillement, écran qui s'allume), `pop` (bulle), `clap` (claquement sec, ordinateur refermé), `thud` (choc sourd), `footsteps` (pas), `swoosh` (souffle court, porte), `whoosh` (souffle long), `ding` (clochette), `click`.

Le mixage est « voix d'abord » : la musique est automatiquement baissée sous la voix (environ 20 dB sous la voix pendant la parole, 12 dB dans les silences) et rien ne sature. Les sons longs (`shimmer` 1,3 s, `whoosh` 1,1 s, `ding` 1,5 s, `footsteps`) doivent être suivis d'une `[pause]` assez longue pour ne pas couvrir la phrase suivante.

**Traduire une description de voix off** (souvent écrite pour un générateur vidéo) : appliquer ce qui correspond à une option — langue, homme/femme et grave/clair (voir les voix), débit (`--speed`), pauses avant les chutes (`[pause]`, `…`), thème musical le plus proche, bruitages cités — et **dire clairement à l'utilisateur ce qui ne peut pas être suivi** : accent régional (belge, du sud…), émotion (sourire, ton complice), respirations, qualité « enregistrement au téléphone », absence totale de son synthétique. Garder les mots exacts demandés ; seules les graphies de prononciation `{affiché|prononcé}` sont permises, pour les sigles et les mots étrangers (« {Project X|Prodjèkt ex} »).

**Pour une vidéo** : avec plusieurs segments, de la musique ou des bruitages, le script écrit `<nom>.timeline.json` — début et fin de chaque phrase, instant de chaque bruitage, en secondes depuis le début du fichier. Le transmettre au skill ou à l'outil vidéo pour caler les images sur la voix. `--stems` écrit en plus `<nom>.voice.wav`, `<nom>.music.wav` et `<nom>.sfx.wav`, déjà aux niveaux du mix, pour un montage où chaque piste reste réglable.

Avec musique ou bruitages, le mix est en 48 kHz : en WAV, la chaîne devient énorme (≈ 130 000 caractères base64 par seconde). Préférer MP3 ou Opus.

## Sorties

Pour `--name message --audio-format opus --encoding base85` :

| Fichier | Contenu |
|---|---|
| `message.opus` | l'audio (`.wav`, `.mp3` ou `.opus` ; l'Opus est en conteneur Ogg) |
| `message.opus.b85.txt` | la chaîne (`.b64`, `.b32`, `.b85`, `.b91` selon l'encodage) |
| `message.opus.datauri.txt` | `data:audio/ogg;base64,…` si `--data-uri` (toujours en base64, voir plus bas) |
| `message.timeline.json` | chronologie des phrases et bruitages (plusieurs segments, musique ou bruitages) |
| `message.voice.wav`, `.music.wav`, `.sfx.wav` | pistes séparées si `--stems` |

Le script affiche un résumé JSON (moteur, voix, durée, tailles, nombre de caractères, empreinte SHA-256, notes éventuelles), pas la chaîne.

## Choisir le format et l'encodage

Mesures sur une phrase de 5,6 secondes, voix kokoro (nombre de caractères de la chaîne) :

| Format | Qualité | base32 | base64 | base85 | basE91 |
|---|---|---|---|---|---|
| WAV | — | 430 976 | 359 144 | 336 695 | 330 110 |
| MP3 | haute | 91 216 | 76 012 | 71 260 | 70 069 |
| MP3 | normale | 27 392 | 22 828 | 21 400 | 21 026 |
| MP3 | compacte | 18 336 | 15 276 | 14 320 | 14 058 |
| Opus | haute | 36 552 | 30 456 | 28 552 | 28 012 |
| Opus | normale | 22 520 | 18 764 | 17 592 | 17 229 |
| Opus | compacte (8 kbit/s) | 8 544 | 7 120 | 6 674 | 6 485 |

**Le format audio pèse beaucoup plus que l'encodage** : passer de WAV à Opus divise la chaîne par 15 à 50, passer de base64 à basE91 ne la réduit que de 8 %. Quand l'utilisateur veut « plus court », agir d'abord sur le format et la qualité.

**Format** (le WAV reste le défaut quand rien n'est précisé) :
- **WAV** : non compressé, lisible partout, mais énorme.
- **MP3** : lisible partout (vieux lecteurs, tous navigateurs).
- **Opus** : le plus compact, excellent pour la voix ; lisible par les navigateurs modernes, moins par les vieux lecteurs. `compacte` (8 kbit/s) dégrade un peu le timbre mais reste intelligible.
- Si l'utilisateur parle de chaîne trop longue, de limite de taille ou d'intégration web : MP3 ou Opus d'emblée.

**Encodage** :
- **base64** : le choix par défaut, et **le seul que les navigateurs décodent nativement** (data URI, `atob`). Toute intégration web passe par lui.
- **base32** (A-Z, 2-7) : insensible à la casse, sûr dans les noms de fichiers, URL ou dictée ; le plus long.
- **base85** (variante RFC 1924, `base64.b85encode` en Python) : 6 % plus court que base64, sans `"` ni `\`, donc utilisable tel quel dans du JSON ; contient `< > & ;`, à échapper en HTML/XML. Le destinataire doit avoir un décodeur (natif en Python).
- **basE91** : le plus compact en ASCII (8 % de moins que base64), mais contient `"`, donc à échapper en JSON ou entre guillemets, et il faut un décodeur (fourni dans `scripts/textcodecs.py`).

Les encodages Unicode (base2048, base32768…) font moins de *caractères* mais plus d'*octets* ; ils ne servent que si la limite porte sur un nombre de caractères (un tweet, par exemple). Ils ne sont pas inclus.

`--data-uri` écrit toujours du base64, même avec un autre `--encoding`, parce que les navigateurs n'acceptent que lui dans un data URI. Le préciser à l'utilisateur dans ce cas.

## Ne pas coller la chaîne dans le chat

Même compressée, une chaîne fait des milliers de caractères : elle noie la conversation et peut être tronquée à la copie. Livrer la chaîne **en fichier**. Ne l'afficher dans le message que si elle fait moins de ~2 000 caractères, ou si l'utilisateur la demande explicitement (`--print`). Pour une intégration web, montrer un exemple de balise avec un data URI abrégé, du type `<audio controls src="data:audio/ogg;base64,T2dnUw…">`.

## Décoder une chaîne reçue

```bash
python3 <skill>/scripts/verify_roundtrip.py chaine.txt --encoding base64 --decode-to sortie.<wav|mp3|opus>
```
Le script reconnaît le format audio d'après les premiers octets (champ `format` du résultat ; relancer avec la bonne extension si besoin). Il ignore les retours à la ligne et les préfixes `data:…;base64,`. Si l'encodage n'est pas connu, essayer base64 puis les autres : un mauvais choix échoue vite avec « décodage impossible ».

## Ce que la vérification garantit

`verify_roundtrip.py` contrôle la structure complète du fichier (en-tête RIFF du WAV, page de fin du flux Ogg, trames MP3 entières), puis décode réellement l'audio. Une chaîne tronquée ou altérée est refusée, avec la raison : la relayer telle quelle.

Un cas limite : un MP3 qui ne vient pas de ce skill et n'a pas de marqueur de fin. Une coupure tombant pile entre deux trames y est alors indétectable ; le script renvoie `ok` avec un champ `warning`. Le mentionner à l'utilisateur. Les MP3 produits par ce skill se terminent par une étiquette ID3v1 (ignorée par les lecteurs) qui sert de marqueur.

## Cas particuliers

- **Texte vide** : le script échoue avec un message clair ; demander un texte.
- **Voix masculine en français** : utiliser `fm_siwis` (ou ses variantes). Ne pas utiliser les voix masculines d'autres langues (`em_alex`, `im_nicola`…) pour du français : elles gardent un accent étranger qui fait plus synthétique.

**Comment `fm_siwis` est obtenue** : Kokoro ne fournit qu'une voix française. Le skill synthétise avec la voix française d'origine, puis applique la fonction « Change gender » de Praat (paquet pip `praat-parselmouth`) : hauteur et formants abaissés, durées et forme de l'intonation conservées. Le rythme et la mélodie des phrases restent exactement ceux de la voix française, d'où l'absence d'accent (mesures : rythme identique, intonation corrélée à 0,98, hauteur 213 → 120 Hz, formants abaissés de 11 à 21 %).

Ne pas fabriquer de voix masculine en déplaçant tout le vecteur de style vers des voix d'homme d'autres langues : sa seconde moitié règle la prosodie, et ce déplacement importe la façon de parler de ces voix (rythme modifié de 5,6 %, intonation corrélée à 0,84 seulement), entendue comme un accent. `fm_siwis_timbre` ne déplace que la moitié timbre, avec une direction homme − femme moyenne sur 9 paires de voix (`assets/voices/gender_direction.bin`).
- **Langue non gérée par kokoro** (allemand, néerlandais…) : repli automatique sur espeak ; prévenir que la voix sera robotique.
- **Réseau bloqué vers PyPI ou npm** : kokoro est indisponible, repli sur espeak (qui a lui-même besoin de pip une fois) ; relayer la note.
- **Clonage de voix, voix d'une personne réelle** : hors de portée de ce skill ; l'expliquer simplement.

Licences : Kokoro-82M et ses voix sont sous Apache 2.0 (voir `assets/voices/NOTICE.md`).
