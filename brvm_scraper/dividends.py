"""
Annonces de dividendes et calcul du rendement (dividend yield).

C'est le module le plus important pour une stratégie BRVM :
la BRVM est avant tout un marché de RENDEMENT, pas de plus-value spectaculaire.
Le rendement du dividende (dividende / cours) est l'indicateur clé.

Source : bandeau d'annonces de la page d'accueil + page des annonces émetteurs.
Format observé : "SIB : Paiement de dividendes le 31 juillet 2026, 425 F CFA par action"
"""

import re
from datetime import datetime
from bs4 import BeautifulSoup

from .client import get_html
from .quotes import get_quotes

_MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

# Ex : "CIE CI : Paiement de dividendes le 28 juillet 2026, 234 FCFA par action"
#
# Le nom de l'émetteur est composé UNIQUEMENT de majuscules, chiffres, points,
# apostrophes, tirets et espaces (ex: "TOTAL SENEGAL S.A.", "CIE CI", "SIB").
# On l'ancre strictement pour éviter d'aspirer le texte qui précède dans le flux
# (les cotations "TTLS 4 260 0,24%" ou le "par action" de l'annonce précédente).
_DIV_RE = re.compile(
    r"(?<![A-Za-zÀ-ÿ])([A-ZÉÈÀÂÎÔÛ][A-ZÉÈÀÂÎÔÛ0-9.'\- ]{1,40}?)"
    r"\s*:\s*Paiement de dividendes"
    r"\s+le\s+(\d{1,2})\s+([a-zéûôA-Z]+)\s+(\d{4})\s*,\s*"
    r"([\d\s]+(?:,\d+)?)\s*F\s?CFA"
)

# Correspondance nom d'émetteur -> ticker du bandeau.
# Les annonces utilisent le nom commercial, le bandeau utilise le ticker.
NOM_VERS_TICKER = {
    "SONATEL": "SNTS", "CIE CI": "CIEC", "CIE": "CIEC", "SIB": "SIBC",
    "BIIC": "BICB", "SERVAIR ABIDJAN CI": "ABJC", "SERVAIR ABIDJAN": "ABJC",
    "TOTAL SENEGAL S.A.": "TTLS", "TOTAL SENEGAL": "TTLS",
    "TOTAL CI": "TTLC", "SGBCI": "SGBC", "ECOBANK CI": "ECOC",
    "ETI": "ETIT", "ORANGE CI": "ORAC", "SOLIBRA": "SLBC",
    "BOA BENIN": "BOAB", "BOA BURKINA FASO": "BOABF", "BOA COTE D'IVOIRE": "BOAC",
    "BOA MALI": "BOAM", "BOA NIGER": "BOAN", "BOA SENEGAL": "BOAS",
    "ONATEL": "ONTBF", "CORIS BANK INTERNATIONAL": "CBIBF",
    "PALMCI": "PALC", "SAPH": "SPHC", "SUCRIVOIRE": "SCRC",
    "NESTLE CI": "NTLC", "NSIA BANQUE CI": "NSBC", "SODE CI": "SDCC",
    "UNILEVER CI": "UNLC", "SETAO": "STAC", "SITAB": "STBC",
    "FILTISAC": "FTSC", "BERNABE": "BNBC", "CFAO CI": "CFAC",
    "AGL CI": "ABJC", "TRACTAFRIC MOTORS CI": "PRSC",
    "VIVO ENERGY CI": "SHEC", "SICABLE": "SICC", "SMB": "SMBC",
    "AIR LIQUIDE CI": "SIVC", "SAFCA": "SAFC", "CROWN SIEM": "SEMC",
    "LOTERIE NATIONALE DU BENIN": "LNBB", "LNB": "LNBB",
    "SODECI": "SDCC", "SAPH CI": "SPHC", "UNIWAX": "UNXC",
    "SUCRES ET DENREES": "SDSC", "BICI CI": "BICC", "SOGB": "SOGC",
    "CABLE CI": "CABC", "NEI CEDA": "NEIC",
}


def _norm_montant(s: str) -> float:
    return float(s.replace(" ", "").replace("\xa0", "").replace(",", "."))


def _parse_date(jour: str, mois: str, annee: str) -> str | None:
    m = _MOIS.get(mois.lower())
    if not m:
        return None
    try:
        return datetime(int(annee), m, int(jour)).date().isoformat()
    except ValueError:
        return None


def _resolve_ticker(nom: str) -> str | None:
    nom_clean = nom.strip().upper().rstrip(".")
    if nom_clean in NOM_VERS_TICKER:
        return NOM_VERS_TICKER[nom_clean]
    # Correspondance partielle
    for cle, ticker in NOM_VERS_TICKER.items():
        if cle in nom_clean or nom_clean in cle:
            return ticker
    return None


def get_dividend_announcements() -> list[dict]:
    """Extrait les annonces de paiement de dividendes du bandeau d'annonces."""
    html = get_html("/fr")
    soup = BeautifulSoup(html, "html.parser")
    texte = soup.get_text(" ", strip=True)

    annonces: list[dict] = []
    vus: set[tuple] = set()

    for m in _DIV_RE.finditer(texte):
        nom = m.group(1).strip(" -|")
        date_iso = _parse_date(m.group(2), m.group(3), m.group(4))
        montant = _norm_montant(m.group(5))
        cle = (nom, date_iso, montant)
        if cle in vus:
            continue
        vus.add(cle)

        annonces.append({
            "emetteur": nom,
            "ticker": _resolve_ticker(nom),
            "date_paiement": date_iso,
            "dividende_fcfa_par_action": montant,
        })

    return sorted(annonces, key=lambda a: a["date_paiement"] or "9999")


def compute_dividend_yield() -> list[dict]:
    """
    Croise les annonces de dividendes avec les cours actuels
    pour calculer le rendement (%) = dividende / cours * 100.

    ATTENTION : ce rendement est basé sur UNE annonce de dividende.
    Certaines sociétés versent un acompte + un solde (2 paiements/an).
    Le rendement annuel réel peut donc être supérieur au chiffre calculé ici.
    À vérifier dans le rapport annuel de la société.
    """
    cours = {q["symbole"]: q["cours_fcfa"] for q in get_quotes()}
    resultats = []

    for a in get_dividend_announcements():
        t = a["ticker"]
        if not t or t not in cours or not cours[t]:
            continue
        prix = cours[t]
        rendement = round(a["dividende_fcfa_par_action"] / prix * 100, 2)
        resultats.append({
            **a,
            "cours_actuel_fcfa": prix,
            "rendement_pct": rendement,
            "avertissement": "Basé sur une seule annonce ; vérifier si acompte ou solde.",
        })

    return sorted(resultats, key=lambda r: r["rendement_pct"], reverse=True)
