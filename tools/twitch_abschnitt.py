#!/usr/bin/env python3
"""Lädt einen Abschnitt aus einem Twitch-VOD.

In der Cloud-Umgebung erreicht ffmpeg die Twitch-Server nicht über den Proxy,
deshalb holt dieses Skript die HLS-Stücke mit Python und setzt sie mit ffmpeg zusammen.

Aufruf:
  python3 tools/twitch_abschnitt.py <VOD-Link> <Start> <Ende> <Ausgabe.mp4> [Format]

Start und Ende als Sekunden oder hh:mm:ss, Format wie bei yt-dlp (Standard: best[height<=1080]).
Bestehende Ausgabedateien werden nicht überschrieben.
"""
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

import requests


def sekunden(wert: str) -> float:
    teile = [float(t) for t in wert.split(":")]
    s = 0.0
    for t in teile:
        s = s * 60 + t
    return s


def main() -> None:
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    link, start, ende, ausgabe = sys.argv[1], sekunden(sys.argv[2]), sekunden(sys.argv[3]), sys.argv[4]
    fmt = sys.argv[5] if len(sys.argv) > 5 else "best[height<=1080]"
    if ende <= start:
        sys.exit("Ende muss nach dem Start liegen.")
    if os.path.exists(ausgabe):
        sys.exit(f"{ausgabe} gibt es schon, nichts überschrieben.")

    url = subprocess.run(["yt-dlp", "-f", fmt, "--get-url", link],
                         capture_output=True, text=True, check=True).stdout.strip().splitlines()[0]
    liste = requests.get(url, timeout=30).text.splitlines()

    init, stuecke, t, dauer = None, [], 0.0, 0.0
    for zeile in liste:
        if zeile.startswith("#EXT-X-MAP:"):
            init = urllib.parse.urljoin(url, re.search(r'URI="([^"]+)"', zeile).group(1))
        elif zeile.startswith("#EXTINF:"):
            dauer = float(zeile[8:].split(",")[0])
        elif zeile and not zeile.startswith("#"):
            stuecke.append((t, urllib.parse.urljoin(url, zeile)))
            t += dauer
    auswahl = [(s, u) for i, (s, u) in enumerate(stuecke)
               if s < ende and (stuecke[i + 1][0] if i + 1 < len(stuecke) else t) > start]
    if not auswahl:
        sys.exit("Der Zeitraum liegt außerhalb des VODs.")

    erstes = auswahl[0][0]
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as roh:
        if init:
            roh.write(requests.get(init, timeout=30).content)
        for _, u in auswahl:
            roh.write(requests.get(u, timeout=60).content)
        rohpfad = roh.name
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", rohpfad,
                        "-ss", f"{start - erstes:.3f}", "-t", f"{ende - start:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac",
                        "-movflags", "+faststart", ausgabe], check=True)
    finally:
        os.remove(rohpfad)
    print(f"Fertig: {ausgabe} ({ende - start:.1f} s ab {sys.argv[2]})")


if __name__ == "__main__":
    main()
