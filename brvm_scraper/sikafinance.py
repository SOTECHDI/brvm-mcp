"""
Scraper pour Sika Finance (sikafinance.com).

Données complémentaires vs brvm.org :
  - Cours d'ouverture, plus haut, plus bas du jour (OHLC)
  - Volume en titres et en valeur XOF
  - Dividendes à venir (source complémentaire à brvm.org)
"""

import re
from bs4 import BeautifulSoup

from .client import get_html

SF_BASE = "https://www.sikafinance.com"

# Ex: /marches/cotation_SDSC.ci -> ticker=SDSC, pays=ci
_HREF_RE = re.compile(r"/marches/cotation_([A-Z]{3,5})\.", re.IGNORECASE)

_TICKER_RE = re.compile(r"^[A-Z]{3,5}$")


def _num(s: str) -> float | None:
    """Convertit un nombre Sika Finance en float.

    Sika utilise l'espace comme séparateur de milliers (format FR).
    Ex : '2 790' -> 2790.0, '-0.72%' -> -0.72, '22 096 290' -> 22096290.0
    """
    if not s:
        return None
    s = (
        s.strip()
        .replace("%", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(" ", "")
    )
    if not s or s in ("-", "—", "n/a", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int_or_none(v: float | None) -> int | None:
    return int(v) if v is not None else None


def get_quotes_sikafinance() -> list[dict]:
    """
    Cotations OHLC depuis Sika Finance.

    Retourne par titre :
      - ouverture_fcfa : cours d'ouverture
      - haut_fcfa : plus haut du jour
      - bas_fcfa : plus bas du jour
      - volume_titres : volume en nombre de titres
      - volume_xof : volume en valeur (XOF)
      - cours_cloture_fcfa : dernier cours (clôture)
      - variation_pct : variation en %

    Ces données OHLC sont absentes de brvm.org.
    """
    html = get_html(f"{SF_BASE}/marches/aaz")
    soup = BeautifulSoup(html, "html.parser")

    quotes = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        joined = " ".join(headers)
        # La table de cotations contient ouverture ou variation
        if "ouverture" not in joined and "variation" not in joined:
            continue

        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue

            # Ticker depuis le lien href
            link = cells[0].find("a", href=True)
            if not link:
                continue
            m = _HREF_RE.search(link["href"])
            if not m:
                continue
            ticker = m.group(1).upper()

            texts = [td.get_text(strip=True) for td in cells]

            # Colonnes (ordre observé) :
            # [0] Nom (lien) | [1] Ouverture | [2] +Haut | [3] +Bas
            # [4] Volume titres | [5] Volume XOF | [6] Dernier | [7] Variation
            def _c(i: int) -> str:
                return texts[i] if i < len(texts) else ""

            quotes.append({
                "symbole": ticker,
                "nom": link.get_text(strip=True),
                "ouverture_fcfa": _int_or_none(_num(_c(1))),
                "haut_fcfa": _int_or_none(_num(_c(2))),
                "bas_fcfa": _int_or_none(_num(_c(3))),
                "volume_titres": _int_or_none(_num(_c(4))),
                "volume_xof": _int_or_none(_num(_c(5))),
                "cours_cloture_fcfa": _int_or_none(_num(_c(6))),
                "variation_pct": _num(_c(7)),
            })

    return quotes


def get_dividends_sikafinance() -> list[dict]:
    """
    Dividendes à venir depuis Sika Finance (source complémentaire à brvm.org).
    """
    html = get_html(f"{SF_BASE}/marches/dividendes")
    soup = BeautifulSoup(html, "html.parser")

    dividends = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        joined = " ".join(headers)
        if "dividende" not in joined and "coupon" not in joined and "montant" not in joined:
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 3 or not cells[0]:
                continue

            entry: dict = {"source": "sikafinance"}
            # Mapping générique par position selon ce qu'on trouve
            for i, h in enumerate(headers):
                if i < len(cells):
                    entry[h or f"col_{i}"] = cells[i]
            dividends.append(entry)

    return dividends
