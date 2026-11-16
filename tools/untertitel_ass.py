#!/usr/bin/env python3
"""Macht aus Wortzeiten eine .ass-Datei mit Wort-für-Wort-Hervorhebung.

Aufruf:
  python3 tools/untertitel_ass.py <woerter.json> <ausgabe.ass>

woerter.json: Liste von {"w": Wort, "s": Start, "e": Ende} in Sekunden, wie faster-whisper sie liefert.
Stil nach dem Untertitel-Skill: 1 bis 3 Wörter je Einblendung, weiß mit schwarzem Rand,
das gesprochene Wort gelb, unteres Mittelfeld mit etwa 25 % Abstand von unten (1080x1920).
"""
import json
import sys

SCHRIFT = "League Spartan Black"
GROESSE = 110
RAND = 8
ABSTAND_UNTEN = 480  # 25 % von 1920
MAX_WOERTER = 3
GELB = r"{\c&H00FFFF&}"  # ASS-Farben sind BGR
WEISS = r"{\c&HFFFFFF&}"

KOPF = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Wort,{SCHRIFT},{GROESSE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{RAND},0,2,60,60,{ABSTAND_UNTEN},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def zeit(s: float) -> str:
    cs = int(round(s * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def gruppen(woerter: list[dict]) -> list[list[dict]]:
    """Teilt in Gruppen von höchstens drei Wörtern, nach Satzzeichen oder Pausen neu beginnen."""
    alle, akt = [], []
    for i, w in enumerate(woerter):
        akt.append(w)
        pause = i + 1 < len(woerter) and woerter[i + 1]["s"] - w["e"] > 0.5
        if len(akt) == MAX_WOERTER or w["w"][-1:] in ".,!?" or pause:
            alle.append(akt)
            akt = []
    if akt:
        alle.append(akt)
    return alle


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    woerter = [w for w in json.load(open(sys.argv[1], encoding="utf-8")) if w["w"].strip()]
    zeilen = []
    for g in gruppen(woerter):
        for i, w in enumerate(g):
            ende = g[i + 1]["s"] if i + 1 < len(g) else w["e"]
            text = " ".join((GELB if j == i else WEISS) + x["w"].upper() for j, x in enumerate(g))
            zeilen.append(f"Dialogue: 0,{zeit(w['s'])},{zeit(max(ende, w['s'] + 0.05))},Wort,,0,0,0,,{text}")
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(KOPF + "\n".join(zeilen) + "\n")
    print(f"{len(zeilen)} Einblendungen in {sys.argv[2]}")


if __name__ == "__main__":
    main()
