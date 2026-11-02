r"""Encodages binaire -> texte utilisés par le skill (bibliothèque standard + basE91 en Python pur).

| nom     | surcoût | alphabet                                   | remarque                                   |
|---------|---------|--------------------------------------------|--------------------------------------------|
| base64  | +33 %   | A-Z a-z 0-9 + / =                          | seul décodé nativement par les navigateurs |
| base32  | +60 %   | A-Z 2-7 =                                  | insensible à la casse                      |
| base85  | +25 %   | 0-9 A-Z a-z !#$%&()*+-;<=>?@^_`{|}~        | variante RFC 1924 (base64.b85encode)       |
| base91  | ~+23 %  | ASCII imprimable sauf - \ ' et espace      | basE91 ; contient " : à échapper en JSON   |
"""
import base64

_B91 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&()*+,./:;<=>?@[]^_`{|}~"'
_B91_DEC = {c: i for i, c in enumerate(_B91)}

EXTENSIONS = {"base64": "b64", "base32": "b32", "base85": "b85", "base91": "b91"}


def _b91_encode(data):
    b = n = 0
    out = []
    for byte in data:
        b |= byte << n
        n += 8
        if n > 13:
            v = b & 8191
            if v > 88:
                b >>= 13
                n -= 13
            else:
                v = b & 16383
                b >>= 14
                n -= 14
            out.append(_B91[v % 91] + _B91[v // 91])
    if n:
        out.append(_B91[b % 91])
        if n > 7 or b > 90:
            out.append(_B91[b // 91])
    return "".join(out)


def _b91_decode(text):
    v = -1
    b = n = 0
    out = bytearray()
    for c in text:
        if c not in _B91_DEC:
            raise ValueError(f"caractère {c!r} hors de l'alphabet basE91")
        p = _B91_DEC[c]
        if v < 0:
            v = p
            continue
        v += p * 91
        b |= v << n
        n += 13 if (v & 8191) > 88 else 14
        while True:
            out.append(b & 255)
            b >>= 8
            n -= 8
            if not n > 7:
                break
        v = -1
    if v + 1:
        out.append((b | v << n) & 255)
    return bytes(out)


def encode(data, scheme):
    if scheme == "base64":
        return base64.b64encode(data).decode("ascii")
    if scheme == "base32":
        return base64.b32encode(data).decode("ascii")
    if scheme == "base85":
        return base64.b85encode(data).decode("ascii")
    if scheme == "base91":
        return _b91_encode(data)
    raise ValueError(f"encodage inconnu : {scheme}")


def decode(text, scheme):
    """Décode une chaîne ; les espaces et retours à la ligne sont ignorés (texte coupé avec --wrap)."""
    text = "".join(text.split())
    if scheme == "base64":
        return base64.b64decode(text, validate=True)
    if scheme == "base32":
        return base64.b32decode(text)
    if scheme == "base85":
        return base64.b85decode(text)
    if scheme == "base91":
        return _b91_decode(text)
    raise ValueError(f"encodage inconnu : {scheme}")
