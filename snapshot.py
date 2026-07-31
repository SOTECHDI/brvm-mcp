#!/usr/bin/env python3
"""
Point d'entrée pour l'historisation quotidienne BRVM.

À brancher sur un cron, après le fixing (séance unique, ~10h45 GMT).
Exemple de crontab (tous les jours ouvrés à 12h00, heure de Ouagadougou = GMT) :

    0 12 * * 1-5  cd /chemin/brvm-mcp && /chemin/.venv/bin/python snapshot.py >> snapshot.log 2>&1

Usage manuel :
    python snapshot.py            # capture le jour
    python snapshot.py --stats    # affiche l'état de la base sans capturer
"""

import sys
import json
from datetime import datetime

from brvm_scraper.storage import snapshot_daily, db_stats


def main() -> int:
    if "--stats" in sys.argv:
        print(json.dumps(db_stats(), ensure_ascii=False, indent=2))
        return 0

    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        resume = snapshot_daily()
        print(f"[{horodatage}] OK — {resume['titres_enregistres']} titres, "
              f"{resume['indices_enregistres']} indices, "
              f"{resume['dividendes_vus']} dividendes "
              f"(séance {resume['date_seance']})")
        return 0
    except Exception as e:
        print(f"[{horodatage}] ÉCHEC — {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
