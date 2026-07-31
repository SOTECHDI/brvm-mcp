"""
Extraction des données fondamentales depuis les PDF de la BRVM
(Bulletin Officiel de la Cote, rapports annuels des sociétés).

Séparation stricte :
  - EXTRACTION : pdfplumber transforme le PDF en tableaux/texte bruts.
  - ANALYSE    : fonctions PURES qui transforment ces bruts en données
                 structurées. Testables sans PDF, calibrables facilement.

Pourquoi les fondamentaux comptent : le cours seul ne dit pas si une action est
chère. Le PER (cours / bénéfice par action) et le rendement (dividende / cours)
permettent de comparer les valeurs entre elles. Un PER de 8 est « bon marché »,
un PER de 25 est « cher » — toutes choses égales par ailleurs.

⚠️ CALIBRAGE REQUIS : les motifs de détection de colonnes ci-dessous sont fondés
sur le format habituel des bulletins financiers francophones. Ils DOIVENT être
vérifiés sur un vrai BOC (voir _COLUMN_KEYWORDS et la fonction diagnose_pdf).
"""

import io
import re

import pdfplumber

from .client import get_pdf

# Mots-clés d'en-tête → champ normalisé. La détection est insensible à la casse
# et aux accents ; on cherche une correspondance partielle dans l'en-tête.
# À ENRICHIR après inspection d'un vrai BOC via diagnose_pdf().
_COLUMN_KEYWORDS = {
    "symbole": ["symbole", "ticker", "code", "valeur"],
    "cours": ["cours", "clôture", "cloture", "dernier"],
    "per": ["per", "price earning", "p/e"],
    "rendement": ["rendement", "yield", "div/cours"],
    "capitalisation": ["capitalisation", "capi", "market cap"],
    "bpa": ["bpa", "bénéfice par action", "benefice par action", "eps"],
    "dividende": ["dividende", "dividend", "coupon"],
}


def _strip_accents(s: str) -> str:
    table = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")
    return s.lower().translate(table)


def _to_number(cell: str | None) -> float | None:
    """Convertit une cellule de bulletin FR en nombre. '1 234,56' -> 1234.56."""
    if cell is None:
        return None
    s = str(cell).strip()
    if not s or s in ("-", "—", "n/a", "nd", "ns"):
        return None
    # Retire tout sauf chiffres, séparateurs, signe
    s = re.sub(r"[^\d,.\-\s]", "", s)
    s = s.replace("\xa0", "").replace("\u202f", "").replace(" ", "")
    if not s or s == "-":
        return None
    # Format FR : virgule décimale. Si les deux séparateurs, le point = millier.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def detect_columns(header_row: list[str]) -> dict[str, int]:
    """
    Associe chaque champ connu à l'index de colonne correspondant dans l'en-tête.
    Fonction pure : testable directement sur une liste d'en-têtes.
    """
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        if not cell:
            continue
        h = _strip_accents(str(cell))
        for field, keywords in _COLUMN_KEYWORDS.items():
            if field in mapping:
                continue
            if any(_strip_accents(kw) in h for kw in keywords):
                mapping[field] = idx
                break
    return mapping


# Mots en majuscules qui ressemblent à un ticker mais sont des lignes de synthèse.
_LIGNES_SYNTHESE = {"TOTAL", "TOTAUX", "MOYENNE", "GLOBAL", "SOUS", "CUMUL", "INDICE"}


def parse_fundamentals_table(table: list[list[str]]) -> list[dict]:
    """
    Transforme un tableau brut (liste de lignes) en fondamentaux structurés.
    Cherche la ligne d'en-tête, mappe les colonnes, puis parse chaque ligne.
    Fonction pure : c'est le cœur testable du module.
    """
    if not table or len(table) < 2:
        return []

    # Trouve la ligne d'en-tête : celle qui mappe le plus de champs connus.
    best_idx, best_map = 0, {}
    for i, row in enumerate(table[:5]):  # l'en-tête est dans les 5 premières lignes
        m = detect_columns(row)
        if len(m) > len(best_map):
            best_idx, best_map = i, m

    if "symbole" not in best_map:
        return []  # sans colonne symbole, impossible d'ancrer les lignes

    resultats = []
    for row in table[best_idx + 1:]:
        if not row or len(row) <= best_map["symbole"]:
            continue
        sym_cell = row[best_map["symbole"]]
        if not sym_cell:
            continue
        sym = str(sym_cell).strip().upper()
        # Un ticker BRVM : 3 à 5 lettres. Filtre les lignes de total/sous-titre.
        if not re.fullmatch(r"[A-Z]{3,5}", sym) or sym in _LIGNES_SYNTHESE:
            continue

        entry = {"symbole": sym}
        for field, col in best_map.items():
            if field == "symbole":
                continue
            val = row[col] if col < len(row) else None
            entry[field] = _to_number(val)
        resultats.append(entry)

    return resultats


def extract_tables(pdf_bytes: bytes) -> list[list[list[str]]]:
    """Extraction brute de tous les tableaux d'un PDF (thin wrapper pdfplumber)."""
    tables = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables():
                if tbl:
                    tables.append(tbl)
    return tables


def extract_text(pdf_bytes: bytes, max_pages: int = 5) -> str:
    """Extraction du texte brut (pour diagnostic ou parsing de secours)."""
    parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:max_pages]:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def get_fundamentals(pdf_url: str) -> list[dict]:
    """
    Télécharge un PDF (BOC ou rapport) et en extrait les fondamentaux par titre.
    Parcourt tous les tableaux, garde ceux qui contiennent une colonne symbole.
    """
    pdf_bytes = get_pdf(pdf_url)
    tables = extract_tables(pdf_bytes)

    agrege: dict[str, dict] = {}
    for tbl in tables:
        for entry in parse_fundamentals_table(tbl):
            sym = entry["symbole"]
            # Fusionne les infos si un titre apparaît dans plusieurs tableaux,
            # en ne remplaçant jamais une valeur non nulle par un None.
            if sym not in agrege:
                agrege[sym] = entry
            else:
                for k, v in entry.items():
                    if v is not None:
                        agrege[sym][k] = v

    return list(agrege.values())


def diagnose_pdf(pdf_url: str) -> dict:
    """
    Outil de CALIBRAGE. Télécharge un PDF et rapporte ce que pdfplumber y voit :
    nombre de tableaux, en-têtes détectés, mapping de colonnes obtenu, et un
    aperçu du texte. À lancer sur un vrai BOC pour ajuster _COLUMN_KEYWORDS.
    """
    pdf_bytes = get_pdf(pdf_url)
    tables = extract_tables(pdf_bytes)
    rapport = {
        "nb_tableaux": len(tables),
        "tableaux": [],
        "apercu_texte": extract_text(pdf_bytes, max_pages=1)[:800],
    }
    for i, tbl in enumerate(tables[:10]):
        header = tbl[0] if tbl else []
        rapport["tableaux"].append({
            "index": i,
            "nb_lignes": len(tbl),
            "en_tete": header,
            "colonnes_detectees": detect_columns(header),
            "exemple_ligne": tbl[1] if len(tbl) > 1 else None,
        })
    return rapport
