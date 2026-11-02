---
tags: [tts-audio-base64]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

J'envoie un son dans un champ JSON via mon API et chaque octet compte. Fais-moi « Alerte : intrusion détectée sur le VLAN 20 » le plus compact possible, mais ça doit rester de l'ASCII que je peux mettre tel quel entre guillemets dans du JSON, sans échappement. Le serveur est en Python.
