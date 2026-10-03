"""
Vérifie UNE fois le prix Kelerog sur leskamas.com, compare avec le dernier
relevé (state.json) et envoie une notification ntfy si le prix a changé.
Prévu pour tourner dans GitHub Actions (le workflow le relance toutes les 5 min).
"""

import json
import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL = "https://www.leskamas.com/vendre-des-kamas.html"
SERVEUR = "Kelerog"
ETAT = "state.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # fourni par les Secrets GitHub

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

MOTIF = re.compile(
    SERVEUR
    + r"\s+([\d.,]+)\s*€/M"
    + r"\s+([\d.,]+)\s*€/M"
    + r"\s+([\d.,]+)\s*Usd/M"
    + r"\s+([\d.,]+)\s*Dhs/M"
    + r"\s+([\d.,]+)\s*CNY/M"
    + r"\s*(\S+)?",
    re.IGNORECASE,
)


def nombre(s):
    return float(s.replace(",", "."))


def lire_prix():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    texte = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    m = MOTIF.search(texte)
    if not m:
        return None
    return {
        "prix1": nombre(m.group(1)),
        "prix2": nombre(m.group(2)),
        "dhs": m.group(4),
        "statut": m.group(6) or "?",
    }


def charger_etat():
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def sauver_etat(p):
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)


def resume(p):
    return (
        f"{SERVEUR} : {p['prix1']}€/M (2e prix : {p['prix2']}€/M) "
        f"| {p['dhs']} Dhs/M | statut : {p['statut']}"
    )


def notifier(titre, message, tag):
    print(f"NOTIF : {titre} -> {message}")
    if not NTFY_TOPIC:
        print("NTFY_TOPIC absent : notification non envoyée.")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": titre, "Tags": tag, "Priority": "high"},
            timeout=15,
        )
    except Exception as e:
        print("Erreur ntfy :", e)


def main():
    heure = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    try:
        p = lire_prix()
    except Exception as e:
        print(f"[{heure}] erreur de lecture : {e}")
        return
    if p is None:
        print(f"[{heure}] {SERVEUR} introuvable (format de la page changé ?)")
        return

    ancien = charger_etat()
    if ancien is None:
        print(f"[{heure}] Premier relevé -> {resume(p)}")
    elif p["prix1"] > ancien["prix1"]:
        notifier(f"{SERVEUR} : prix en hausse",
                 f"{ancien['prix1']}€/M -> {p['prix1']}€/M\n{resume(p)}", "arrow_up")
    elif p["prix1"] < ancien["prix1"]:
        notifier(f"{SERVEUR} : prix en baisse",
                 f"{ancien['prix1']}€/M -> {p['prix1']}€/M\n{resume(p)}", "arrow_down")
    elif p["prix2"] != ancien["prix2"] or p["statut"] != ancien["statut"]:
        notifier(f"{SERVEUR} : changement", resume(p), "information_source")
    else:
        print(f"[{heure}] inchangé -> {resume(p)}")

    if ancien != p:
        sauver_etat(p)


if __name__ == "__main__":
    main()
