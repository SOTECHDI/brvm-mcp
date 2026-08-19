"""
brvm-mcp — Serveur MCP donnant accès aux données publiques de la BRVM
(Bourse Régionale des Valeurs Mobilières, marché boursier de l'UEMOA).

Sources de données :
  - brvm.org        : cotations officielles, sociétés, dividendes, PDF BOC
  - afx.kwayisi.org : volumes, fondamentaux par ticker, historique HTML, indices sectoriels
  - richbourse.com  : cours veille, capitalisation par titre
  - sikafinance.com : OHLC (ouverture/haut/bas)

Transports disponibles (variable MCP_TRANSPORT) :
  stdio            → Claude Desktop / Claude Code (défaut)
  streamable-http  → API HTTP, Docker, réseau local
  sse              → Server-Sent Events, clients MCP legacy

Note sur l'async : FastMCP utilise anyio en interne et exécute automatiquement
les outils `def` synchrones dans un thread pool (anyio.to_thread.run_sync).
Les outils sont donc définis comme des fonctions synchrones ordinaires — c'est
le pattern recommandé pour éviter tout conflit asyncio/anyio.

AVERTISSEMENT : outil d'information et d'analyse. Ne constitue pas un conseil
en investissement. Le conseil en investissement est une activité réglementée
dans l'UEMOA (agrément AMF-UMOA requis).
"""

import json
import logging
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from brvm_scraper.rate_limiter import (
    current_identifier,
    check_rate_limit,
    rate_limit_error,
)

from brvm_scraper import (
    get_quotes,
    get_market_summary,
    list_companies,
    get_company,
    get_dividend_announcements,
    compute_dividend_yield,
    PAYS_SLUGS,
    get_quotes_afx,
    get_fundamentals_afx,
    get_history_afx,
    get_sector_indices_afx,
    get_quotes_richbourse,
    get_quotes_sikafinance,
    get_dividends_sikafinance,
)
from brvm_scraper.storage import get_price_history, get_performance, db_stats
from brvm_scraper.fundamentals import get_fundamentals, diagnose_pdf

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("brvm-mcp")

mcp = FastMCP("brvm")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Extrait l'IP du client et la stocke dans current_identifier."""
    async def dispatch(self, request: Request, call_next):
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown"
        )
        current_identifier.set(ip)
        return await call_next(request)


def _rl() -> str | None:
    """
    Vérifie la limite de taux pour le client courant.
    Retourne un message d'erreur JSON si la limite est dépassée, None sinon.
    En mode stdio (identifier=None), aucune limite n'est appliquée.
    """
    identifier = current_identifier.get()
    if not identifier:
        return None  # mode stdio — pas de limite
    result = check_rate_limit(identifier)
    if not result["allowed"]:
        log.warning(f"Rate limit atteint pour {identifier}")
        return rate_limit_error()
    return None

DISCLAIMER = (
    "Données publiques BRVM fournies à titre informatif. "
    "Ne constitue pas un conseil en investissement (activité réglementée AMF-UMOA). "
    "Les performances passées ne préjugent pas des performances futures."
)


@mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
async def server_card(request: Request) -> JSONResponse:
    """Smithery server card — permet la découverte sans scan OAuth."""
    return JSONResponse({
        "name": "brvm-mcp",
        "description": "MCP server exposing BRVM (West African stock exchange) public data via 18 tools aggregating 4 sources: brvm.org, AFX Kwayisi, Rich Bourse, Sika Finance.",
        "tools": [
            {"name": "brvm_market_summary", "description": "Market overview: BRVM-C, BRVM-30, BRVM-Prestige indices, market cap, top/worst movers"},
            {"name": "brvm_quotes", "description": "Prices (FCFA) and % change — all 47 tickers or a specific one"},
            {"name": "brvm_list_companies", "description": "Listed companies, filterable by country"},
            {"name": "brvm_company_details", "description": "Company profile + PDF document links"},
            {"name": "brvm_dividends", "description": "Upcoming dividend payments"},
            {"name": "brvm_dividend_yield", "description": "Dividend yield ranked highest first"},
            {"name": "brvm_price_history", "description": "Historical prices from local SQLite database"},
            {"name": "brvm_performance", "description": "Price performance over the tracked period"},
            {"name": "brvm_history_status", "description": "Database depth and coverage"},
            {"name": "brvm_fundamentals", "description": "P/E ratio, EPS, market cap from BOC PDF"},
            {"name": "brvm_diagnose_pdf", "description": "PDF structure diagnostic"},
            {"name": "brvm_volumes", "description": "Trading volumes from AFX Kwayisi (absent from brvm.org)"},
            {"name": "brvm_fondamentaux_ticker", "description": "P/E, EPS, dividend yield per ticker — no PDF needed"},
            {"name": "brvm_historique_avec_volumes", "description": "Last 10 sessions with volumes"},
            {"name": "brvm_indices_sectoriels", "description": "Sector indices: Energy, Financial Services, Public Utilities (day/1WK/YTD)"},
            {"name": "brvm_cotations_enrichies", "description": "Previous close + market cap per ticker (Rich Bourse)"},
            {"name": "brvm_ohlc", "description": "Open/High/Low/Close + volumes (Sika Finance)"},
            {"name": "brvm_dividendes_sikafinance", "description": "Cross-check dividend announcements (Sika Finance)"},
        ]
    })


def _ok(data) -> str:
    return json.dumps(
        {"data": data, "avertissement": DISCLAIMER},
        ensure_ascii=False,
        indent=2,
    )


def _err(msg: str) -> str:
    return json.dumps({"erreur": msg}, ensure_ascii=False)


# =============================================================================
# OUTILS BRVM.ORG — SOURCE OFFICIELLE
# =============================================================================


@mcp.tool()
def brvm_market_summary() -> str:
    """
    Vue d'ensemble du marché BRVM : valeur des indices (BRVM-Composite,
    BRVM-30, BRVM-Prestige), capitalisation boursière, valeur des
    transactions du jour, et les 5 plus fortes hausses / baisses.
    À utiliser pour prendre le pouls général du marché.
    """
    if err := _rl(): return err
    try:
        return _ok(get_market_summary())
    except Exception as e:
        log.exception("market_summary")
        return _err(f"Échec récupération du résumé marché : {e}")


@mcp.tool()
def brvm_quotes(ticker: str = "") -> str:
    """
    Cotations de la BRVM : cours en FCFA et variation en % de la séance.

    Args:
        ticker: symbole d'une société (ex: SNTS, ONTBF, CBIBF, BOABF).
                Laisser vide pour obtenir les 47 titres cotés.
    """
    if err := _rl(): return err
    try:
        q = get_quotes(ticker or None)
        if ticker and not q:
            return _err(f"Ticker '{ticker}' introuvable. Appelez brvm_quotes() sans argument pour la liste complète.")
        return _ok(q)
    except Exception as e:
        log.exception("quotes")
        return _err(f"Échec récupération des cotations : {e}")


@mcp.tool()
def brvm_list_companies(pays: str = "") -> str:
    """
    Liste des sociétés cotées à la BRVM avec leurs coordonnées et le lien
    vers leur fiche officielle.

    Args:
        pays: filtre optionnel. Valeurs acceptées : Bénin, Burkina Faso,
              Côte d'Ivoire, Guinée Bissau, Mali, Niger, Sénégal, Togo.
    """
    if err := _rl(): return err
    try:
        return _ok(list_companies(pays or None))
    except ValueError as e:
        return _err(f"{e}")
    except Exception as e:
        log.exception("list_companies")
        return _err(f"Échec récupération des sociétés : {e}")


@mcp.tool()
def brvm_company_details(slug: str) -> str:
    """
    Fiche détaillée d'une société cotée, incluant les liens vers ses
    documents PDF publiés (rapports annuels, communiqués).

    Args:
        slug: identifiant de la société tel que renvoyé par
              brvm_list_companies (ex: 'bank-africa-burkina-faso').
    """
    if err := _rl(): return err
    try:
        return _ok(get_company(slug))
    except Exception as e:
        log.exception("company_details")
        return _err(f"Échec récupération de la fiche '{slug}' : {e}")


@mcp.tool()
def brvm_dividends() -> str:
    """
    Annonces de paiement de dividendes à venir : émetteur, ticker,
    date de paiement, montant en FCFA par action.
    """
    if err := _rl(): return err
    try:
        return _ok(get_dividend_announcements())
    except Exception as e:
        log.exception("dividends")
        return _err(f"Échec récupération des dividendes : {e}")


@mcp.tool()
def brvm_dividend_yield() -> str:
    """
    Rendement du dividende par société : dividende annoncé / cours actuel,
    classé du plus élevé au plus faible. Indicateur clé sur la BRVM, qui est
    avant tout un marché de rendement.

    Note : le calcul se base sur une annonce de dividende. Certaines sociétés
    versent un acompte puis un solde ; le rendement annuel réel peut être
    supérieur. Vérifier dans le rapport annuel de la société.
    """
    if err := _rl(): return err
    try:
        return _ok(compute_dividend_yield())
    except Exception as e:
        log.exception("dividend_yield")
        return _err(f"Échec calcul des rendements : {e}")


@mcp.tool()
def brvm_price_history(symbole: str, limit: int = 90) -> str:
    """
    Historique des cours d'un titre (nécessite d'avoir historisé via snapshot.py).
    Renvoie les cours du plus récent au plus ancien.

    Args:
        symbole: ticker (ex: SNTS, ONTBF, CBIBF).
        limit: nombre maximum de séances à renvoyer (défaut 90).
    """
    if err := _rl(): return err
    try:
        hist = get_price_history(symbole, limit)
        if not hist:
            return _err(
                f"Aucun historique pour '{symbole}'. La base se remplit jour "
                f"après jour via snapshot.py — patientez quelques séances."
            )
        return _ok(hist)
    except Exception as e:
        log.exception("price_history")
        return _err(f"Échec lecture historique : {e}")


@mcp.tool()
def brvm_performance(symbole: str) -> str:
    """
    Performance d'un titre sur toute la période historisée : variation en FCFA
    et en %, entre le premier et le dernier cours enregistré en base.

    Args:
        symbole: ticker (ex: SNTS, ONTBF, CBIBF).
    """
    if err := _rl(): return err
    try:
        perf = get_performance(symbole)
        if not perf:
            return _err(
                f"Pas assez d'historique pour '{symbole}' (2 séances minimum)."
            )
        return _ok(perf)
    except Exception as e:
        log.exception("performance")
        return _err(f"Échec calcul performance : {e}")


@mcp.tool()
def brvm_history_status() -> str:
    """
    État de la base d'historique : profondeur (première/dernière séance),
    nombre de séances couvertes, titres suivis. Utile pour savoir si l'on a
    assez de recul pour analyser des tendances.
    """
    if err := _rl(): return err
    try:
        return _ok(db_stats())
    except Exception as e:
        log.exception("history_status")
        return _err(f"Échec lecture de l'état de la base : {e}")


@mcp.tool()
def brvm_fundamentals(pdf_url: str) -> str:
    """
    Extrait les données fondamentales par société (PER, rendement, capitalisation,
    BPA) depuis un PDF de la BRVM : Bulletin Officiel de la Cote ou rapport annuel.

    Le PER (cours / bénéfice par action) mesure la cherté d'une action : bas = bon
    marché, élevé = cher. À comparer entre sociétés d'un même secteur.

    Args:
        pdf_url: URL du PDF. Récupérable via brvm_company_details
                 (champ 'documents_pdf') ou depuis la rubrique BOC du site.
    """
    if err := _rl(): return err
    try:
        data = get_fundamentals(pdf_url)
        if not data:
            return _err(
                "Aucun tableau de fondamentaux détecté dans ce PDF. "
                "Lancez brvm_diagnose_pdf sur la même URL pour inspecter sa structure."
            )
        return _ok(data)
    except Exception as e:
        log.exception("fundamentals")
        return _err(f"Échec extraction des fondamentaux : {e}")


@mcp.tool()
def brvm_diagnose_pdf(pdf_url: str) -> str:
    """
    Outil de diagnostic/calibrage : montre ce que l'extracteur voit dans un PDF
    (nombre de tableaux, en-têtes, colonnes détectées, aperçu du texte). À utiliser
    si brvm_fundamentals ne trouve rien, pour comprendre la structure du document.

    Args:
        pdf_url: URL du PDF à inspecter.
    """
    if err := _rl(): return err
    try:
        return _ok(diagnose_pdf(pdf_url))
    except Exception as e:
        log.exception("diagnose_pdf")
        return _err(f"Échec du diagnostic PDF : {e}")


# =============================================================================
# OUTILS SOURCES COMPLÉMENTAIRES
# =============================================================================


@mcp.tool()
def brvm_volumes(ticker: str = "") -> str:
    """
    Volumes d'échange depuis AFX Kwayisi — absents de brvm.org.
    Indispensable pour évaluer la liquidité d'un titre avant d'y investir.

    Args:
        ticker: symbole (ex: SNTS, ETIT). Vide = tous les titres.
    """
    if err := _rl(): return err
    try:
        data = get_quotes_afx()
        if ticker:
            t = ticker.strip().upper()
            data = [q for q in data if q["symbole"] == t]
            if not data:
                return _err(f"Ticker '{ticker}' introuvable sur AFX Kwayisi.")
        return _ok(data)
    except Exception as e:
        log.exception("volumes")
        return _err(f"Échec récupération des volumes : {e}")


@mcp.tool()
def brvm_fondamentaux_ticker(ticker: str) -> str:
    """
    Fondamentaux d'un titre depuis AFX Kwayisi — sans télécharger de PDF.

    Retourne : PER, BPA (bénéfice par action), dividende par action,
    rendement du dividende, actions en circulation, capitalisation boursière.

    Le PER mesure la cherté d'une action : PER bas = bon marché,
    PER élevé = cher. À comparer entre sociétés du même secteur.

    Args:
        ticker: symbole (ex: SNTS, ONTBF, CBIBF).
    """
    if err := _rl(): return err
    try:
        return _ok(get_fundamentals_afx(ticker))
    except Exception as e:
        log.exception("fondamentaux_ticker")
        return _err(f"Échec récupération des fondamentaux de '{ticker}' : {e}")


@mcp.tool()
def brvm_historique_avec_volumes(ticker: str) -> str:
    """
    Historique des 10 dernières séances d'un titre avec volumes, depuis AFX Kwayisi.

    Complète brvm_price_history (base locale) en ajoutant les volumes
    et sans nécessiter d'avoir fait tourner snapshot.py au préalable.

    Args:
        ticker: symbole (ex: SNTS, ONTBF, CBIBF).
    """
    if err := _rl(): return err
    try:
        data = get_history_afx(ticker)
        if not data:
            return _err(f"Aucun historique trouvé pour '{ticker}' sur AFX Kwayisi.")
        return _ok(data)
    except Exception as e:
        log.exception("historique_avec_volumes")
        return _err(f"Échec lecture historique AFX de '{ticker}' : {e}")


@mcp.tool()
def brvm_indices_sectoriels() -> str:
    """
    Indices sectoriels BRVM depuis AFX Kwayisi.

    Expose les performances jour / 1 semaine / YTD par secteur :
    Energie, Services Financiers, Public Utilities, etc.
    Absents de brvm.org qui ne publie que BRVM-C, BRVM-30 et BRVM-Prestige.
    """
    if err := _rl(): return err
    try:
        return _ok(get_sector_indices_afx())
    except Exception as e:
        log.exception("indices_sectoriels")
        return _err(f"Échec récupération des indices sectoriels : {e}")


@mcp.tool()
def brvm_cotations_enrichies() -> str:
    """
    Cotations enrichies depuis Rich Bourse.

    En plus du cours du jour, retourne pour chaque titre :
      - cours_veille_fcfa : cours de clôture de la veille
      - capitalisation_fcfa : capitalisation boursière
      - volume et valeur des transactions

    Utile pour croiser avec les cotations officielles brvm.org.
    """
    if err := _rl(): return err
    try:
        return _ok(get_quotes_richbourse())
    except Exception as e:
        log.exception("cotations_enrichies")
        return _err(f"Échec récupération des cotations Rich Bourse : {e}")


@mcp.tool()
def brvm_ohlc() -> str:
    """
    Cotations OHLC (Open/High/Low/Close) depuis Sika Finance.

    Retourne pour chaque titre :
      ouverture, plus haut, plus bas, clôture, volume titres, volume XOF.

    Ces données intraday sont absentes de brvm.org.
    Rappel : la BRVM fonctionne en séance unique (fixing ~10h45 GMT),
    donc le haut et le bas reflètent les ordres de la séance, pas du temps réel.
    """
    if err := _rl(): return err
    try:
        return _ok(get_quotes_sikafinance())
    except Exception as e:
        log.exception("ohlc")
        return _err(f"Échec récupération des données OHLC : {e}")


@mcp.tool()
def brvm_dividendes_sikafinance() -> str:
    """
    Dividendes à venir depuis Sika Finance (source complémentaire à brvm.org).

    Utile pour croiser avec brvm_dividends() afin de ne manquer aucune annonce.
    """
    if err := _rl(): return err
    try:
        return _ok(get_dividends_sikafinance())
    except Exception as e:
        log.exception("dividendes_sikafinance")
        return _err(f"Échec récupération des dividendes Sika Finance : {e}")


# =============================================================================
# POINT D'ENTRÉE — SÉLECTION DU TRANSPORT PAR VARIABLE D'ENVIRONNEMENT
# =============================================================================

def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    host = os.getenv("MCP_HOST", "0.0.0.0")
    # Railway injecte $PORT automatiquement — priorité sur MCP_PORT
    port = int(os.getenv("PORT", os.getenv("MCP_PORT", "8000")))

    log.info(f"Démarrage brvm-mcp — transport={transport}")

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("streamable-http", "sse"):
        # Dans mcp>=1.28, host/port se configurent via mcp.settings
        mcp.settings.host = host
        mcp.settings.port = port
        # Désactiver la protection DNS rebinding localhost-only pour les
        # déploiements cloud (Railway, Fly.io, etc.) — le TLS du proxy suffit
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        log.info(f"Écoute sur http://{host}:{port} — rate limit: 25 appels/jour (tier gratuit)")
        # Injection du middleware de rate limiting
        try:
            import uvicorn
            starlette_app = mcp.get_app(transport=transport)
            starlette_app.add_middleware(RateLimitMiddleware)
            uvicorn.run(starlette_app, host=host, port=port)
        except (AttributeError, TypeError):
            # Fallback si get_app() n'est pas disponible dans cette version
            log.warning("Middleware rate limiting non activé (get_app() indisponible) — fallback sans IP tracking")
            mcp.run(transport=transport)
    else:
        log.error(
            f"Transport inconnu : {transport!r}. "
            "Valeurs acceptées : stdio | streamable-http | sse"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
