"""
Outils de l'agent BRVM.

On enveloppe les fonctions de brvm_scraper en outils LangChain. Chaque outil a une
description soignée : c'est ce que le LLM lit pour décider quand l'appeler. La
qualité de ces descriptions détermine la qualité du raisonnement de l'agent.
"""

from langchain_core.tools import tool

from brvm_scraper import (
    get_quotes,
    get_market_summary,
    list_companies,
    get_company,
    get_dividend_announcements,
    compute_dividend_yield,
    get_price_history,
    get_performance,
    db_stats,
    get_fundamentals,
    diagnose_pdf,
    # Sources complémentaires : AFX Kwayisi, Rich Bourse, Sika Finance.
    # Elles apportent ce que brvm.org n'expose pas (volumes, OHLC, sectoriels).
    get_quotes_afx,
    get_fundamentals_afx,
    get_history_afx,
    get_sector_indices_afx,
    get_quotes_richbourse,
    get_quotes_sikafinance,
    get_dividends_sikafinance,
)


@tool
def marche_resume() -> dict:
    """Vue d'ensemble du marché BRVM : indices (BRVM-Composite, BRVM-30,
    BRVM-Prestige), capitalisation, valeur des transactions du jour, et les
    5 plus fortes hausses et baisses. À utiliser pour prendre le pouls général."""
    return get_market_summary()


@tool
def cotations(ticker: str = "") -> list:
    """Cours (en FCFA) et variation (%) des titres de la BRVM pour la séance.
    Passer un ticker (ex: SNTS, ONTBF, CBIBF, BOABF) pour un seul titre, ou
    laisser vide pour les 47 valeurs cotées."""
    return get_quotes(ticker or None)


@tool
def societes(pays: str = "") -> list:
    """Liste des sociétés cotées avec coordonnées et lien vers leur fiche.
    Filtre optionnel par pays : Bénin, Burkina Faso, Côte d'Ivoire,
    Guinée Bissau, Mali, Niger, Sénégal, Togo."""
    return list_companies(pays or None)


@tool
def fiche_societe(slug: str) -> dict:
    """Fiche détaillée d'une société cotée et liens vers ses documents PDF
    (rapports annuels, communiqués). Le 'slug' vient de l'outil societes()."""
    return get_company(slug)


@tool
def dividendes() -> list:
    """Annonces de paiement de dividendes à venir : émetteur, ticker, date de
    paiement, montant en FCFA par action."""
    return get_dividend_announcements()


@tool
def rendements_dividende() -> list:
    """Rendement du dividende par société (dividende annoncé / cours actuel),
    classé du plus élevé au plus faible. Indicateur clé sur la BRVM. Attention :
    calculé sur une annonce ; le rendement annuel réel peut être supérieur si la
    société verse un acompte puis un solde."""
    return compute_dividend_yield()


@tool
def historique_cours(symbole: str, limit: int = 90) -> list:
    """Historique des cours d'un titre depuis la base locale (remplie jour après
    jour). Renvoie du plus récent au plus ancien. Vide si l'historisation vient
    de démarrer."""
    return get_price_history(symbole, limit)


@tool
def performance(symbole: str) -> dict:
    """Performance d'un titre sur toute la période historisée : variation en FCFA
    et en %, entre le premier et le dernier cours enregistré."""
    return get_performance(symbole) or {"info": "Historique insuffisant (2 séances min)."}


@tool
def etat_historique() -> dict:
    """État de la base d'historique : première/dernière séance, nombre de séances
    couvertes, titres suivis. Permet de savoir si l'on a assez de recul."""
    return db_stats()


@tool
def fondamentaux(pdf_url: str) -> list:
    """Extrait les fondamentaux (PER, rendement, capitalisation, BPA) depuis un
    PDF de la BRVM (Bulletin Officiel de la Cote ou rapport annuel). L'URL vient
    du champ 'documents_pdf' de fiche_societe(). Le PER mesure la cherté d'une
    action : bas = bon marché, élevé = cher."""
    return get_fundamentals(pdf_url)


# =============================================================================
# SOURCES COMPLÉMENTAIRES (AFX Kwayisi, Rich Bourse, Sika Finance)
# brvm.org ne publie ni les volumes, ni l'OHLC, ni les indices sectoriels.
# Ces outils comblent ces trous ; ils doublonnent parfois les précédents, d'où
# des descriptions qui précisent QUAND préférer l'un à l'autre.
# =============================================================================


@tool
def volumes(ticker: str = "") -> list:
    """VOLUMES et liquidité (source AFX Kwayisi) — absents de brvm.org.
    N'utiliser QUE si la question porte sur le volume, la liquidité ou la
    performance depuis le 1er janvier. Pour un simple cours, utiliser
    cotations(). Un titre peut afficher un cours sans s'échanger : c'est
    précisément ce que révèle cet outil.
    Passer un ticker (ex: SNTS) ou laisser vide pour tous."""
    donnees = get_quotes_afx()
    if ticker:
        t = ticker.strip().upper()
        donnees = [q for q in donnees if q.get("symbole") == t]
        if not donnees:
            return [{"info": f"Ticker '{ticker}' introuvable sur AFX Kwayisi."}]
    return donnees


@tool
def fondamentaux_ticker(ticker: str) -> dict:
    """Fondamentaux d'un titre par son ticker, SANS télécharger de PDF :
    PER, BPA, dividende par action, rendement, actions en circulation,
    capitalisation. À préférer à fondamentaux() qui exige une URL de PDF.
    Le PER mesure la cherté d'une action ; il se compare entre sociétés d'un
    même secteur."""
    return get_fundamentals_afx(ticker)


@tool
def historique_avec_volumes(ticker: str) -> list:
    """Historique des 10 dernières séances d'un titre AVEC les volumes
    (source AFX Kwayisi). À utiliser quand la base locale est encore vide ou
    quand les volumes sont nécessaires ; sinon historique_cours() offre une
    profondeur bien plus grande."""
    donnees = get_history_afx(ticker)
    return donnees or [{"info": f"Aucun historique AFX pour '{ticker}'."}]


@tool
def indices_sectoriels() -> list:
    """Indices sectoriels de la BRVM (finance, industrie, distribution,
    services publics, transport, agriculture...). Permet de situer un titre
    par rapport à la tendance de son secteur, et non du seul indice global."""
    return get_sector_indices_afx()


@tool
def cotations_enrichies() -> list:
    """COURS DE VEILLE et CAPITALISATION par titre (source Rich Bourse).
    N'utiliser QUE si la question porte sur le cours de clôture précédent, la
    capitalisation d'une société, ou pour recouper une donnée douteuse avec une
    seconde source. Pour un simple cours du jour, utiliser cotations()."""
    return get_quotes_richbourse()


@tool
def ohlc() -> list:
    """AMPLITUDE DE SÉANCE — ouverture, plus haut, plus bas, clôture (source
    Sika Finance). N'utiliser QUE si la question porte sur l'amplitude, la
    volatilité intra-séance, ou un cours d'ouverture. Pour le seul dernier
    cours, utiliser cotations()."""
    return get_quotes_sikafinance()


@tool
def dividendes_sikafinance() -> list:
    """Dividendes à venir selon Sika Finance. Source complémentaire à
    dividendes() : les calendriers diffèrent parfois entre les deux, et un
    écart mérite d'être signalé plutôt que tranché."""
    return get_dividends_sikafinance()


@tool
def diagnostic_pdf(pdf_url: str) -> dict:
    """Diagnostic d'un PDF de la BRVM : montre ce que l'extracteur y voit
    (tableaux, en-têtes, colonnes, aperçu du texte). À utiliser uniquement
    quand fondamentaux() ne renvoie rien, pour comprendre pourquoi."""
    return diagnose_pdf(pdf_url)


# Liste ordonnée des outils exposés à l'agent (parité avec les 18 outils MCP)
TOOLS = [
    # Données officielles — brvm.org
    marche_resume,
    cotations,
    societes,
    fiche_societe,
    dividendes,
    rendements_dividende,
    historique_cours,
    performance,
    etat_historique,
    fondamentaux,
    # Sources complémentaires
    diagnostic_pdf,
    volumes,
    fondamentaux_ticker,
    historique_avec_volumes,
    indices_sectoriels,
    cotations_enrichies,
    ohlc,
    dividendes_sikafinance,
]
