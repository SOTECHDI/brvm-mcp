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


# Liste ordonnée des outils exposés à l'agent
TOOLS = [
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
]
