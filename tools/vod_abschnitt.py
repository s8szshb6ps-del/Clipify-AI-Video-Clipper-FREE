#!/usr/bin/env python3
"""Lädt einen Abschnitt aus einem Twitch- oder Kick-VOD.

In der Cloud-Umgebung erreicht ffmpeg die Videoserver nicht über den Proxy,
deshalb holt dieses Skript die HLS-Stücke mit Python und setzt sie mit ffmpeg zusammen.

Aufruf:
  python3 tools/vod_abschnitt.py <VOD-Link> <Start> <Ende> <Ausgabe.mp4> [max. Höhe]

VOD-Link:
  Twitch: https://www.twitch.tv/videos/<id>
  Kick:   https://kick.com/<kanal>/videos/<uuid>
  oder direkt ein .m3u8-Link
Start und Ende als Sekunden oder hh:mm:ss. Max. Höhe Standard 1080, 0 = kleinste Qualität (zum Testen).
Bestehende Ausgabedateien werden nicht überschrieben.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse

import requests

KOPF = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SITZUNG = requests.Session()


def holen(url: str, timeout: int = 60) -> requests.Response:
    """GET mit bis zu fünf Versuchen, weil lange Downloads über den Proxy gelegentlich abbrechen."""
    for versuch in range(5):
        try:
            antwort = SITZUNG.get(url, headers=KOPF, timeout=timeout)
            antwort.raise_for_status()
            return antwort
        except requests.RequestException:
            if versuch == 4:
                raise
            time.sleep(2 * (versuch + 1))
    raise RuntimeError("unerreichbar")


def sekunden(wert: str) -> float:
    s = 0.0
    for t in wert.split(":"):
        s = s * 60 + float(t)
    return s


def m3u8_finden(link: str, max_hoehe: int) -> str:
    if ".m3u8" in link:
        return link
    kick = re.match(r"https?://(?:www\.)?kick\.com/([^/]+)/videos/([0-9a-f-]{36})", link)
    if kick:
        kanal, uuid = kick.groups()
        videos = holen(f"https://kick.com/api/v2/channels/{kanal}/videos", 30).json()
        for v in videos:
            if (v.get("video") or {}).get("uuid") == uuid and v.get("source"):
                return v["source"]
        sys.exit("Kick-VOD nicht in der Videoliste des Kanals gefunden (zu alt oder nur für Abonnenten?).")
    fmt = "worst" if max_hoehe == 0 else f"best[height<={max_hoehe}]"
    return subprocess.run(["yt-dlp", "-f", fmt, "--get-url", link],
                          capture_output=True, text=True, check=True).stdout.strip().splitlines()[0]


def variante_waehlen(url: str, text: str, max_hoehe: int) -> str:
    """Wählt bei einer Master-Playlist die passende Qualität."""
    varianten, info = [], None
    for zeile in text.splitlines():
        if zeile.startswith("#EXT-X-STREAM-INF:"):
            h = re.search(r"RESOLUTION=\d+x(\d+)", zeile)
            info = int(h.group(1)) if h else 0
        elif info is not None and zeile and not zeile.startswith("#"):
            varianten.append((info, urllib.parse.urljoin(url, zeile)))
            info = None
    if not varianten:
        return url
    varianten.sort()
    if max_hoehe == 0:
        return varianten[0][1]
    passend = [v for v in varianten if v[0] <= max_hoehe]
    return (passend or varianten[:1])[-1][1]


def main() -> None:
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    link, start, ende, ausgabe = sys.argv[1], sekunden(sys.argv[2]), sekunden(sys.argv[3]), sys.argv[4]
    max_hoehe = int(sys.argv[5]) if len(sys.argv) > 5 else 1080
    if ende <= start:
        sys.exit("Ende muss nach dem Start liegen.")
    if os.path.exists(ausgabe):
        sys.exit(f"{ausgabe} gibt es schon, nichts überschrieben.")

    url = m3u8_finden(link, max_hoehe)
    text = holen(url, 30).text
    if "#EXT-X-STREAM-INF" in text:
        url = variante_waehlen(url, text, max_hoehe)
        text = holen(url, 30).text

    init, stuecke, t, dauer = None, [], 0.0, 0.0
    for zeile in text.splitlines():
        if zeile.startswith("#EXT-X-MAP:"):
            init = urllib.parse.urljoin(url, re.search(r'URI="([^"]+)"', zeile).group(1))
        elif zeile.startswith("#EXTINF:"):
            dauer = float(zeile[8:].split(",")[0])
        elif zeile and not zeile.startswith("#"):
            stuecke.append((t, t + dauer, urllib.parse.urljoin(url, zeile)))
            t += dauer
    auswahl = [s for s in stuecke if s[0] < ende and s[1] > start]
    if not auswahl:
        sys.exit("Der Zeitraum liegt außerhalb des VODs.")

    endung = ".mp4" if init else ".ts"
    with tempfile.NamedTemporaryFile(suffix=endung, delete=False) as roh:
        if init:
            roh.write(holen(init, 30).content)
        for _, _, u in auswahl:
            roh.write(holen(u, 60).content)
        rohpfad = roh.name
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", rohpfad,
                        "-ss", f"{start - auswahl[0][0]:.3f}", "-t", f"{ende - start:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac",
                        "-movflags", "+faststart", ausgabe], check=True)
    finally:
        os.remove(rohpfad)
    print(f"Fertig: {ausgabe} ({ende - start:.1f} s ab {sys.argv[2]})")


if __name__ == "__main__":
    main()
