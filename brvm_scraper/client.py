"""
Client HTTP pour le site BRVM (https://www.brvm.org)
- Session persistante avec User-Agent identifiable
- Cache TTL simple pour ne pas surcharger le site (politesse)
- Retry basique en cas d'erreur réseau
"""

import time
import requests

BASE_URL = "https://www.brvm.org"

# Cache TTL : les cours BRVM ne bougent qu'une fois par jour ouvré
# (séance unique, fixing ~10h45 GMT). 15 min de cache est largement suffisant.
CACHE_TTL_SECONDS = 15 * 60

_cache: dict[str, tuple[float, str]] = {}

_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "brvm-mcp/0.1 (outil open-source d'analyse BRVM; "
        "contact: dondirechristian@gmail.com)"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
})


def get_html(path: str, use_cache: bool = True, retries: int = 2) -> str:
    """Récupère le HTML d'une page du site BRVM, avec cache TTL."""
    url = path if path.startswith("http") else f"{BASE_URL}{path}"

    if use_cache and url in _cache:
        ts, html = _cache[url]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return html

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = _session.get(url, timeout=30)
            resp.raise_for_status()
            _cache[url] = (time.time(), resp.text)
            return resp.text
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))  # backoff progressif

    raise ConnectionError(f"Impossible de joindre {url} : {last_err}")


def clear_cache() -> None:
    _cache.clear()


def get_pdf(url: str, retries: int = 2) -> bytes:
    """
    Récupère un PDF en bytes (rapports annuels, Bulletins Officiels de la Cote).
    Pas de cache texte ici : les PDF sont volumineux et rarement re-téléchargés
    dans une même session.
    """
    full = url if url.startswith("http") else f"{BASE_URL}{url}"
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = _session.get(full, timeout=60)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "pdf" not in ctype.lower() and not resp.content[:4] == b"%PDF":
                raise ValueError(f"La ressource n'est pas un PDF (Content-Type: {ctype})")
            return resp.content
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise ConnectionError(f"Impossible de télécharger le PDF {full} : {last_err}")
