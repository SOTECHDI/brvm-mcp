"""
Scraper pour AFX Kwayisi (afx.kwayisi.org/brvm/).

Données complémentaires vs brvm.org :
  - Volumes d'échange (brvm.org ne les expose pas)
  - Fondamentaux par ticker sans PDF : PER, BPA, dividende, capitalisation
  - Historique 10 séances en HTML avec volumes
  - Indices sectoriels BRVM (Energie, Services Financiers, etc.)
  - Performance YTD par titre
"""

import re
from bs4 import BeautifulSoup

from .client import get_html

AFX_BASE = "https://afx.kwayisi.org"

# Regex pour les indices sectoriels
# Format actuel : "BRVM Energie (+1.69%; -5.31% 1WK; +44.65% YTD)"
_SECTOR_RE = re.compile(
    r"(BRVM[\w\s]+?)"              # nom du secteur (ex: BRVM Energie)
    r"\s*\("                        # parenthèse ouvrante
    r"([+-]?\d+[\.,]\d+)%"         # variation jour
    r";\s*"
    r"([+-]?\d+[\.,]\d+)%\s*1WK"  # variation 1 semaine
    r";\s*"
    r"([+-]?\d+[\.,]\d+)%\s*YTD"  # performance YTD
    r"\)",                          # parenthèse fermante
    re.IGNORECASE,
)

# Regex pour parser le texte brut de la table principale AFX.
# La table AFX a un HTML mal formé (pas de </tr> entre les lignes) donc
# soup.get_text(" ") sur la TABLE entière donne du texte avec espaces lisibles :
# "ABJC Servair Abidjan Côte d'Ivoire 1,695 2,960 +10 BICB BIIC Bénin ..."
_AFX_HREF_RE = re.compile(r"/brvm/([a-z]{3,5})\.html", re.IGNORECASE)

_AFX_QUOTE_RE = re.compile(
    r"\b([A-Z]{3,5})\b"    # ticker : 3-5 majuscules
    r"\s+"
    r"([^0-9\n]+?)"        # nom société (tout sauf chiffres et retour-ligne)
    r"\s*"                 # permet tirets dans noms : "Bank of Africa - Benin"
    r"([\d,]+)"             # volume (milliers séparés par virgule)
    r"\s+"
    r"([\d,]+)"             # cours FCFA
    r"\s+"
    r"([+\-][\d,]+)",       # variation absolue FCFA (pas de %)
    re.UNICODE,
)


def _num(s: str) -> float | None:
    """Convertit un nombre AFX en float.

    AFX utilise le format US (virgule=milliers, point=décimale).
    Gère aussi les abréviations : 3.15T, 100M, 500B, 1.2K.
    """
    if not s:
        return None
    s = s.strip().lstrip("+").replace("%", "")
    if not s or s in ("-", "—", "n/a", "N/A"):
        return None
    suffixes = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    for suf, mult in suffixes.items():
        if s.endswith(suf):
            try:
                return float(s[:-1].replace(",", "")) * mult
            except ValueError:
                return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _int_or_none(v: float | None) -> int | None:
    return int(v) if v is not None else None


def get_quotes_afx() -> list[dict]:
    """
    Cotations depuis AFX Kwayisi : ticker, nom complet, volume, cours FCFA,
    variation absolue en FCFA.

    Avantage clé : expose les VOLUMES, absents de brvm.org.

    Note technique : AFX utilise une table HTML non standard (les <tr> ne sont
    pas correctement fermés). On identifie la table principale via les liens
    ticker, puis on parse son texte brut avec une regex.
    """
    html = get_html(f"{AFX_BASE}/brvm/")
    soup = BeautifulSoup(html, "html.parser")

    # Trouver la table principale (celle qui contient les ~47 tickers)
    main_table = None
    for table in soup.find_all("table"):
        links = table.find_all("a", href=_AFX_HREF_RE)
        tickers = {
            _AFX_HREF_RE.search(a["href"]).group(1).upper()
            for a in links
            if _AFX_HREF_RE.search(a["href"])
        }
        if len(tickers) >= 40:
            main_table = table
            break

    if not main_table:
        return []

    # get_text(" ") ajoute un espace entre chaque balise HTML → le texte
    # malformé de la table devient lisible : "ABJC Servair Abidjan... 1,695 2,960 +10"
    text = main_table.get_text(" ", strip=True)

    quotes = []
    seen: set[str] = set()

    for m in _AFX_QUOTE_RE.finditer(text):
        ticker = m.group(1)
        if ticker in seen:
            continue
        seen.add(ticker)

        quotes.append({
            "symbole": ticker,
            "nom": m.group(2).strip(),
            "volume": _int_or_none(_num(m.group(3))),
            "cours_fcfa": _int_or_none(_num(m.group(4))),
            "variation_fcfa": _int_or_none(_num(m.group(5))),
        })

    return quotes


def get_fundamentals_afx(ticker: str) -> dict:
    """
    Fondamentaux d'un titre depuis sa fiche AFX.

    Retourne sans avoir besoin de télécharger un PDF :
      PER, BPA, dividende par action, rendement dividende,
      actions en circulation, capitalisation boursière.
    """
    ticker = ticker.strip().upper()
    html = get_html(f"{AFX_BASE}/brvm/{ticker.lower()}.html")
    soup = BeautifulSoup(html, "html.parser")

    result: dict = {"symbole": ticker, "source": "afx.kwayisi.org"}

    # La section fondamentaux utilise des <p> avec <br> :
    # <p>Earnings Per Share<br>4,133.86</p>
    # get_text("|") transforme <br> en "|"
    _fields = {
        "earnings per share": "bpa",
        "price/earning ratio": "per",
        "dividend per share": "dividende_par_action_fcfa",
        "dividend yield": "rendement_dividende_pct",
        "shares outstanding": "actions_en_circulation",
        "market capitalization": "capitalisation_fcfa",
    }
    for p in soup.find_all("p"):
        text = p.get_text("|", strip=True)
        lower = text.lower()
        for keyword, field in _fields.items():
            if keyword in lower:
                parts = text.split("|")
                val = _num(parts[-1]) if len(parts) >= 2 else None
                result[field] = val
                break

    return result


def get_history_afx(ticker: str) -> list[dict]:
    """
    Historique des 10 dernières séances d'un titre depuis AFX.
    Inclut les volumes (absents de la base SQLite locale sans snapshot).
    """
    ticker = ticker.strip().upper()
    html = get_html(f"{AFX_BASE}/brvm/{ticker.lower()}.html")
    soup = BeautifulSoup(html, "html.parser")

    history = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        if "date" not in headers or not any("close" in h for h in headers):
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 3 or not cells[0]:
                continue
            cours = _num(cells[2]) if len(cells) > 2 else None
            if cours is None:
                continue
            history.append({
                "date": cells[0],
                "volume": _int_or_none(_num(cells[1])) if len(cells) > 1 else None,
                "cours_fcfa": _int_or_none(cours),
                "variation_fcfa": _int_or_none(_num(cells[3])) if len(cells) > 3 and cells[3] else None,
                "variation_pct": _num(cells[4]) if len(cells) > 4 and cells[4] else None,
            })

    return history


def get_sector_indices_afx() -> list[dict]:
    """
    Indices sectoriels BRVM depuis AFX.

    Unique : brvm.org n'expose que les 3 indices principaux (BRVM-C, BRVM-30, BRVM-PRES).
    AFX expose aussi Energie, Services Financiers, Public Utilities, etc.
    """
    html = get_html(f"{AFX_BASE}/brvm/")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    indices = []
    seen: set[str] = set()
    for m in _SECTOR_RE.finditer(text):
        nom = m.group(1).strip()
        if nom in seen:
            continue
        seen.add(nom)
        indices.append({
            "indice": nom,
            "variation_jour_pct": float(m.group(2).replace(",", ".")),
            "variation_1semaine_pct": float(m.group(3).replace(",", ".")),
            "performance_ytd_pct": float(m.group(4).replace(",", ".")),
        })

    return indices
