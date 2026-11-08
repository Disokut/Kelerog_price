"""
Vérifie UNE fois le prix Kelerog sur leskamas.com, compare avec le dernier
relevé (state.json) et envoie une notification ntfy si le prix a changé.
Prévu pour tourner dans GitHub Actions (le workflow le relance toutes les 5 min).

Mise à jour refonte du site : les prix sont dans un <table> ; chaque ligne est
  <th scope="row"><a>Kelerog</a></th>
  <td>€2.950/M</td>   (Paypal / Skrill / SEPA)   -> prix1
  <td>€2.920/M</td>   (Bitcoin)                   -> prix2
  <td>3.245 USDT/M</td>
  <td>32.450 DH/M</td>                            -> dhs
  <td>21.682 CNY/M</td>
  <td>Achat | Complet</td>                        -> statut
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

NOMBRE = re.compile(r"\d[\d.,]*")
MOT = re.compile(r"[A-Za-zÀ-ÿ]+")


def nombre(s):
    m = NOMBRE.search(s)
    if not m:
        raise ValueError(f"pas de nombre dans {s!r}")
    return float(m.group(0).replace(",", "."))


def trouver_ligne(soup):
    """Retrouve la <tr> du serveur via sa cellule d'en-tête de ligne."""
    for th in soup.find_all("th", attrs={"scope": "row"}):
        if th.get_text(strip=True).lower() == SERVEUR.lower():
            return th.find_parent("tr")
    return None


def parser_html(html):
    soup = BeautifulSoup(html, "html.parser")
    ligne = trouver_ligne(soup)
    if ligne is None:
        return None
    cellules = [td.get_text(" ", strip=True) for td in ligne.find_all("td")]
    if len(cellules) < 6:
        return None
    mot = MOT.search(cellules[5])
    return {
        "prix1": nombre(cellules[0]),
        "prix2": nombre(cellules[1]),
        "dhs": f"{nombre(cellules[3]):.3f}",
        "statut": mot.group(0) if mot else "?",
    }


def lire_prix():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return parser_html(r.text)


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
