# Voix embarquée

`ff_siwis.bin` est le vecteur de style de la voix française « siwis » du modèle de synthèse
**Kokoro-82M v1.0** (hexgrad), copié sans modification depuis le paquet npm `kokoro-js@1.2.1`
(`voices/ff_siwis.bin`, sha256 `a35f5675ad08948e326ae75fd0ea16ba5d0042e4f76b5f3d1df77d0a48c54861`).

Kokoro-82M et ses voix sont distribués sous licence Apache 2.0 (texte complet :
`LICENSE-kokoro-Apache-2.0.txt`). La voix « siwis » est entraînée sur le corpus SIWIS.

Les poids du modèle (92 Mo) ne sont pas embarqués : `scripts/kokoro_engine.py` les télécharge au
premier usage depuis le registre npm (`kokoro-q8-shards@1.0.0`, copie de `model_quantized.onnx` de
onnx-community/Kokoro-82M-v1.0-ONNX) et vérifie leur empreinte SHA-256. Les autres voix sont
téléchargées de la même façon depuis `kokoro-js@1.2.1`.

## Direction masculine

`gender_direction.bin` (510 × 256 float32, sha256
`cd85eec14f836b5a00d28b5867b8d9df3e6b6d971247643d5701d88e917b7b50`) est calculé à partir des voix de
`kokoro-js@1.2.1` : moyenne, sur les paires af_heart/am_michael, af_bella/am_adam, af_sarah/am_eric,
bf_emma/bm_george, bf_isabella/bm_lewis, ef_dora/em_alex, if_sara/im_nicola, pf_dora/pm_alex et
hf_alpha/hm_omega, de (voix masculine − voix féminine). Seule la voix `fm_siwis_timbre` l'utilise,
et seulement sur la moitié timbre du vecteur (colonnes 0 à 127) : `ff_siwis + 1,3 × direction`.
Les autres voix `fm_siwis*` utilisent `ff_siwis` tel quel ; elles sont rendues masculines après
synthèse par la fonction « Change gender » de Praat (praat-parselmouth, GPL v3, installé par pip et
non redistribué ici). Œuvre dérivée de Kokoro-82M, sous Apache 2.0.
