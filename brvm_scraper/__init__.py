"""brvm_scraper — collecte de données publiques de la BRVM (bourse UEMOA).

Sources :
  - brvm.org        : cotations officielles, sociétés, dividendes, PDF BOC
  - afx.kwayisi.org : volumes, fondamentaux par ticker, historique HTML, indices sectoriels
  - richbourse.com  : cours veille, capitalisation par titre, volume
  - sikafinance.com : OHLC (ouverture/haut/bas), dividendes complémentaires
"""

from .client import clear_cache, get_html
from .quotes import (
    get_quotes,
    get_indices,
    get_market_activity,
    get_market_summary,
)
from .companies import list_companies, get_company, PAYS_SLUGS
from .dividends import get_dividend_announcements, compute_dividend_yield
from .storage import (
    snapshot_daily,
    get_price_history,
    get_performance,
    db_stats,
)
from .fundamentals import get_fundamentals, diagnose_pdf
from .afx_kwayisi import (
    get_quotes_afx,
    get_fundamentals_afx,
    get_history_afx,
    get_sector_indices_afx,
)
from .richbourse import get_quotes_richbourse
from .sikafinance import get_quotes_sikafinance, get_dividends_sikafinance

__version__ = "0.4.0"

__all__ = [
    # brvm.org
    "get_quotes", "get_indices", "get_market_activity", "get_market_summary",
    "list_companies", "get_company", "PAYS_SLUGS",
    "get_dividend_announcements", "compute_dividend_yield",
    "snapshot_daily", "get_price_history", "get_performance", "db_stats",
    "get_fundamentals", "diagnose_pdf",
    "clear_cache", "get_html",
    # afx.kwayisi.org
    "get_quotes_afx", "get_fundamentals_afx", "get_history_afx", "get_sector_indices_afx",
    # richbourse.com
    "get_quotes_richbourse",
    # sikafinance.com
    "get_quotes_sikafinance", "get_dividends_sikafinance",
]
