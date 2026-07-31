"""
Scraper pour Rich Bourse (richbourse.com).

Données complémentaires vs brvm.org :
  - Cours de la veille (permet de vérifier/calculer la variation soi-même)
  - Capitalisation boursière par titre
  - Volume et valeur des transactions par titre
"""

import re
from bs4 import BeautifulSoup

from .client import get_html

RB_BASE = "https://www.richbourse.com"

_TICKER_RE = re.compile(r"^[A-Z]{3,5}$")


def _num(s: str) -> float | None:
    """Convertit un nombre Rich Bourse en float.

    Rich Bourse utilise le format FR : espace=milliers, virgule=décimale.
    Ex : '7 995' -> 7995.0, '2,46 %' -> 2.46, '34 700 160 000' -> 34700160000.0
    Exception : le champ Variation utilise le point décimal : '7.43%' -> 7.43.
    """
    if not s:
        return None
    s = (
        s.strip()
        .replace("%", "")
        .replace("\xa0", "")   # espace insécable
        .replace(" ", "")      # espace = séparateur de milliers FR
        .replace(",", ".")     # virgule = décimale FR
    )
    if not s or s in ("-", "—", "n/a"):
        return None
    s = s.replace("−", "-")   # signe Unicode moins
    try:
        return float(s)
    except ValueError:
        return None


def _int_or_none(v: float | None) -> int | None:
    return int(v) if v is not None else None


def get_quotes_richbourse() -> list[dict]:
    """
    Cotations depuis Rich Bourse.

    Retourne par titre :
      - variation_pct : variation en % (avec signe)
      - volume : nombre de titres échangés
      - valeur_transactions_fcfa : valeur totale des transactions
      - cours_actuel_fcfa : cours de clôture du jour
      - cours_veille_fcfa : cours de clôture de la veille (UNIQUE vs brvm.org)
      - capitalisation_fcfa : capitalisation boursière du titre
    """
    html = get_html(f"{RB_BASE}/common/variation/index")
    soup = BeautifulSoup(html, "html.parser")

    quotes = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        joined = " ".join(headers)
        if "variation" not in joined or "cours" not in joined:
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 9:
                continue
            # Colonnes réelles (première colonne vide, ticker en [1]) :
            # [0]∅  [1]Symbole  [2]Action(nom)  [3]Variation%  [4]Volume
            # [5]Valeur(FCFA)  [6]Valeur%  [7]Cours actuel  [8]Cours veille
            # [9]Capitalisation  [10]∅
            symbole = cells[1].strip().upper()
            if not _TICKER_RE.match(symbole):
                continue

            def _cell(idx: int) -> str:
                return cells[idx].strip() if idx < len(cells) else ""

            quotes.append({
                "symbole": symbole,
                "nom": _cell(2),
                "variation_pct": _num(_cell(3)),
                "volume": _int_or_none(_num(_cell(4))),
                "valeur_transactions_fcfa": _int_or_none(_num(_cell(5))),
                "cours_actuel_fcfa": _int_or_none(_num(_cell(7))),
                "cours_veille_fcfa": _int_or_none(_num(_cell(8))),
                "capitalisation_fcfa": _int_or_none(_num(_cell(9))),
            })

    return quotes
