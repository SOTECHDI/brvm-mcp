"""
Parsing de la liste des sociétés cotées à la BRVM.

Source : /fr/emetteurs/societes-cotees  (paginée : ?page=0..4)
Filtres pays disponibles : /fr/pays-societes-cotees/<slug>

Chaque société a une fiche détaillée dont l'URL est de la forme :
/fr/emetteurs/societes-cotees/<slug-de-la-societe>
"""

import re
from bs4 import BeautifulSoup

from .client import get_html, BASE_URL

PAYS_SLUGS = {
    "benin": "benin",
    "burkina faso": "burkina-faso",
    "burkina": "burkina-faso",
    "cote d'ivoire": "cote-divoire",
    "côte d'ivoire": "cote-divoire",
    "civ": "cote-divoire",
    "guinee bissau": "guinee-bissau",
    "guinée bissau": "guinee-bissau",
    "mali": "mali",
    "niger": "niger",
    "senegal": "senegal",
    "sénégal": "senegal",
    "togo": "togo",
}

_SOC_HREF_RE = re.compile(r"/(?:fr|en)/emetteurs/societes-cotees/(?!$)([a-z0-9\-]+)$")
_EMAIL_RE = re.compile(r"[\w\.\-\+]+@[\w\-]+\.[\w\.\-]+")
_TEL_RE = re.compile(r"\(\d{3}\)[\d\s/\-]{6,}")


def _parse_page(html: str) -> list[dict]:
    """Extrait les sociétés d'une page de listing."""
    soup = BeautifulSoup(html, "html.parser")
    societes: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        m = _SOC_HREF_RE.search(a["href"])
        if not m:
            continue
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)

        # Le bloc parent contient le nom, le drapeau (pays), l'adresse, les contacts.
        bloc = a.find_parent(["div", "li", "article"]) or a.parent
        texte = bloc.get_text(" ", strip=True) if bloc else ""

        # Nom : le lien porte souvent un logo, donc on remonte au titre du bloc.
        nom = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        if not nom:
            # fallback : première ligne significative du bloc
            nom = texte.split("  ")[0][:120].strip()

        # Pays déduit du nom de l'image drapeau (ex: .../burkina_0.png)
        pays = None
        if bloc:
            for img in bloc.find_all("img", src=True):
                src = img["src"].lower()
                for key in ("benin", "burkina", "ivoire", "mali", "niger",
                            "senegal", "togo", "bissau"):
                    if f"/{key}" in src or f"public/{key}" in src:
                        pays = key
                        break
                if pays:
                    break

        email = _EMAIL_RE.search(texte)
        tel = _TEL_RE.search(texte)

        societes.append({
            "nom": nom,
            "slug": slug,
            "url_fiche": f"{BASE_URL}/fr/emetteurs/societes-cotees/{slug}",
            "pays_indice": pays,
            "email": email.group(0) if email else None,
            "telephone": tel.group(0).strip() if tel else None,
        })

    return societes


def list_companies(pays: str | None = None, max_pages: int = 6) -> list[dict]:
    """
    Retourne la liste des sociétés cotées.
    `pays` (optionnel) : 'burkina faso', 'senegal', 'cote d\\'ivoire', etc.
    """
    if pays:
        slug = PAYS_SLUGS.get(pays.strip().lower())
        if not slug:
            raise ValueError(
                f"Pays inconnu : {pays}. Choix : {sorted(set(PAYS_SLUGS.values()))}"
            )
        base_path = f"/fr/pays-societes-cotees/{slug}"
    else:
        base_path = "/fr/emetteurs/societes-cotees"

    toutes: list[dict] = []
    vus: set[str] = set()

    for page in range(max_pages):
        path = base_path if page == 0 else f"{base_path}?page={page}"
        try:
            html = get_html(path)
        except ConnectionError:
            break

        lot = _parse_page(html)
        nouveaux = [s for s in lot if s["slug"] not in vus]
        if not nouveaux:
            break  # plus rien de neuf => fin de pagination

        for s in nouveaux:
            vus.add(s["slug"])
        toutes.extend(nouveaux)

    return toutes


def get_company(slug: str) -> dict:
    """Récupère la fiche détaillée d'une société via son slug."""
    html = get_html(f"/fr/emetteurs/societes-cotees/{slug}")
    soup = BeautifulSoup(html, "html.parser")

    titre = soup.find("h1")
    contenu = soup.find("div", class_=re.compile(r"content|node|region-content"))
    texte = contenu.get_text("\n", strip=True) if contenu else soup.get_text("\n", strip=True)

    # Liens vers les rapports/documents PDF de la société
    docs = []
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".pdf"):
            href = a["href"]
            docs.append({
                "titre": a.get_text(" ", strip=True) or "document",
                "url": href if href.startswith("http") else f"{BASE_URL}{href}",
            })

    return {
        "slug": slug,
        "nom": titre.get_text(" ", strip=True) if titre else slug,
        "url_fiche": f"{BASE_URL}/fr/emetteurs/societes-cotees/{slug}",
        "contenu": texte[:4000],
        "documents_pdf": docs[:20],
    }
