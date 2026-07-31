"""
Parsing des cotations et indicateurs de marché depuis la page d'accueil BRVM.

Stratégie : le bandeau de cotation est présent dans le HTML brut (Drupal 7,
pas de rendu JS). On utilise des regex robustes sur le TEXTE de la page
plutôt que des sélecteurs CSS fragiles, car la structure du thème peut changer.
Format observé dans le bandeau : "ABJC 3 150 0,00%"
"""

import re
from bs4 import BeautifulSoup

from .client import get_html

# Ticker BRVM : 3 à 5 lettres majuscules (ex: ETIT, BOABF, ONTBF, SNTS)
_QUOTE_RE = re.compile(
    r"\b([A-Z]{3,5})\s+((?:\d{1,3}(?:\s\d{3})*))\s+(-?\d+,\d{2})%"
)

_INDEX_RE = re.compile(
    r"(BRVM-C|BRVM-30|BRVM-PRES)\s*\|?\s*([\d\s]+,\d{2})\s*\|?\s*(-?\d+,\d{2})%"
)

_MARKET_RE = {
    "valeur_transactions_fcfa": re.compile(
        r"Valeur des transactions\s*\|?\s*([\d\s]+)\s*FCFA"
    ),
    "capitalisation_actions_fcfa": re.compile(
        r"Capitalisation Actions\s*\|?\s*([\d\s]+)\s*FCFA"
    ),
    "capitalisation_obligations_fcfa": re.compile(
        r"Capitalisation des obligations\s*\|?\s*([\d\s]+)\s*FCFA"
    ),
}


def _to_int(s: str) -> int:
    return int(s.replace("\u202f", " ").replace(" ", "").replace("\xa0", ""))


def _to_float(s: str) -> float:
    return float(s.replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace(",", "."))


def _page_text() -> str:
    html = get_html("/fr")
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def get_quotes(ticker: str | None = None) -> list[dict]:
    """
    Retourne la liste des cotations du bandeau : symbole, cours (FCFA),
    variation (%). Si `ticker` est fourni, filtre sur ce symbole.
    """
    text = _page_text()
    seen: set[str] = set()
    quotes: list[dict] = []

    for m in _QUOTE_RE.finditer(text):
        sym, price, var = m.group(1), m.group(2), m.group(3)
        # Filtres anti-faux-positifs : les noms d'indices, mois, etc.
        if sym in ("BRVM", "FCFA", "CFA", "GMT"):
            continue
        if sym in seen:
            continue
        seen.add(sym)
        quotes.append({
            "symbole": sym,
            "cours_fcfa": _to_int(price),
            "variation_pct": _to_float(var),
        })

    if ticker:
        t = ticker.strip().upper()
        quotes = [q for q in quotes if q["symbole"] == t]

    return quotes


def get_indices() -> list[dict]:
    """Retourne BRVM-C, BRVM-30 et BRVM-PRES (valeur + variation du jour)."""
    text = _page_text()
    out, seen = [], set()
    for m in _INDEX_RE.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        out.append({
            "indice": name,
            "valeur": _to_float(m.group(2)),
            "variation_pct": _to_float(m.group(3)),
        })
    return out


def get_market_activity() -> dict:
    """Valeur des transactions + capitalisations actions/obligations."""
    text = _page_text()
    result = {}
    for key, rx in _MARKET_RE.items():
        m = rx.search(text)
        result[key] = _to_int(m.group(1)) if m else None
    return result


def get_market_summary() -> dict:
    """Vue synthétique : indices, activité, top/flop du jour."""
    quotes = get_quotes()
    sorted_q = sorted(quotes, key=lambda q: q["variation_pct"], reverse=True)
    return {
        "indices": get_indices(),
        "activite": get_market_activity(),
        "top_5": sorted_q[:5],
        "flop_5": sorted_q[-5:][::-1],
        "nb_titres_cotes": len(quotes),
    }
