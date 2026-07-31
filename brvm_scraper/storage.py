"""
Historisation des données BRVM dans SQLite.

Le site brvm.org n'expose que la séance courante. Pour construire des tendances,
détecter des signaux et faire du backtesting, il FAUT logger les données jour
après jour. Ce module est le socle de tout ce qui suit (analyse, agent).

Conception :
  - SQLite pur (zéro dépendance externe, portable PC ↔ VPS).
  - Idempotent : deux snapshots le même jour de bourse écrasent proprement
    (UPSERT sur clé (date_seance, symbole)). Un cron qui tourne deux fois ne
    duplique rien.
  - On stocke la date de SÉANCE (jour ouvré), pas l'horodatage d'exécution :
    peu importe l'heure à laquelle le cron passe, la donnée du jour est unique.

Usage typique (cron quotidien après le fixing, ~11h GMT) :
    from brvm_scraper.storage import snapshot_daily
    snapshot_daily()
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from .quotes import get_quotes, get_indices
from .dividends import get_dividend_announcements

# Chemin de la base : BRVM_DB env var (Docker/prod) ou racine du projet (dev).
DEFAULT_DB = Path(
    os.getenv("BRVM_DB", str(Path(__file__).resolve().parents[1] / "brvm_history.db"))
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cours_historique (
    date_seance   TEXT NOT NULL,          -- ISO 'YYYY-MM-DD' (jour de bourse)
    symbole       TEXT NOT NULL,
    cours_fcfa    INTEGER NOT NULL,
    variation_pct REAL,
    saisi_le      TEXT NOT NULL,          -- horodatage d'insertion (traçabilité)
    PRIMARY KEY (date_seance, symbole)
);

CREATE TABLE IF NOT EXISTS indices_historique (
    date_seance   TEXT NOT NULL,
    indice        TEXT NOT NULL,
    valeur        REAL NOT NULL,
    variation_pct REAL,
    saisi_le      TEXT NOT NULL,
    PRIMARY KEY (date_seance, indice)
);

CREATE TABLE IF NOT EXISTS dividendes_historique (
    emetteur        TEXT NOT NULL,
    ticker          TEXT,
    date_paiement   TEXT,
    dividende_fcfa  REAL NOT NULL,
    vu_le           TEXT NOT NULL,        -- 1re fois que l'annonce a été captée
    PRIMARY KEY (emetteur, date_paiement, dividende_fcfa)
);

CREATE INDEX IF NOT EXISTS idx_cours_symbole ON cours_historique(symbole);
CREATE INDEX IF NOT EXISTS idx_cours_date    ON cours_historique(date_seance);
"""


@contextmanager
def _connect(db_path: Path | str = DEFAULT_DB):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _seance_date(quotes: list[dict]) -> str:
    """
    Détermine la date de séance à historiser.

    Heuristique : si TOUS les titres affichent 0,00 % de variation, c'est
    qu'aucune cotation n'a encore eu lieu aujourd'hui (le bandeau montre la
    clôture de la veille reportée). On log quand même sous la date du jour ;
    l'UPSERT corrigera au prochain passage si besoin. Cas simple et robuste.
    """
    return date.today().isoformat()


def snapshot_daily(db_path: Path | str = DEFAULT_DB) -> dict:
    """
    Capture l'état du marché du jour (cours + indices + dividendes) et
    l'enregistre. Idempotent : rejouable sans créer de doublon.

    Retourne un petit récapitulatif de ce qui a été écrit.
    """
    now = datetime.now().isoformat(timespec="seconds")
    quotes = get_quotes()
    indices = get_indices()
    dividends = get_dividend_announcements()
    seance = _seance_date(quotes)

    with _connect(db_path) as conn:
        conn.executemany(
            """INSERT INTO cours_historique
               (date_seance, symbole, cours_fcfa, variation_pct, saisi_le)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date_seance, symbole) DO UPDATE SET
                 cours_fcfa    = excluded.cours_fcfa,
                 variation_pct = excluded.variation_pct,
                 saisi_le      = excluded.saisi_le""",
            [(seance, q["symbole"], q["cours_fcfa"], q["variation_pct"], now)
             for q in quotes],
        )

        conn.executemany(
            """INSERT INTO indices_historique
               (date_seance, indice, valeur, variation_pct, saisi_le)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date_seance, indice) DO UPDATE SET
                 valeur        = excluded.valeur,
                 variation_pct = excluded.variation_pct,
                 saisi_le      = excluded.saisi_le""",
            [(seance, i["indice"], i["valeur"], i["variation_pct"], now)
             for i in indices],
        )

        # Dividendes : on ne garde que la 1re capture d'une annonce (vu_le figé).
        conn.executemany(
            """INSERT INTO dividendes_historique
               (emetteur, ticker, date_paiement, dividende_fcfa, vu_le)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(emetteur, date_paiement, dividende_fcfa) DO NOTHING""",
            [(d["emetteur"], d["ticker"], d["date_paiement"],
              d["dividende_fcfa_par_action"], now) for d in dividends],
        )

    return {
        "date_seance": seance,
        "titres_enregistres": len(quotes),
        "indices_enregistres": len(indices),
        "dividendes_vus": len(dividends),
    }


def get_price_history(symbole: str, limit: int = 90,
                      db_path: Path | str = DEFAULT_DB) -> list[dict]:
    """Historique des cours d'un titre, du plus récent au plus ancien."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT date_seance, cours_fcfa, variation_pct
               FROM cours_historique
               WHERE symbole = ?
               ORDER BY date_seance DESC
               LIMIT ?""",
            (symbole.strip().upper(), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_performance(symbole: str, db_path: Path | str = DEFAULT_DB) -> dict | None:
    """
    Performance d'un titre entre son premier et son dernier cours historisés :
    variation absolue et en %, sur la période réellement couverte par la base.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT date_seance, cours_fcfa FROM cours_historique
               WHERE symbole = ? ORDER BY date_seance ASC""",
            (symbole.strip().upper(),),
        ).fetchall()

    if len(rows) < 2:
        return None  # pas assez de points pour mesurer quoi que ce soit

    debut, fin = rows[0], rows[-1]
    p0, p1 = debut["cours_fcfa"], fin["cours_fcfa"]
    return {
        "symbole": symbole.strip().upper(),
        "date_debut": debut["date_seance"],
        "date_fin": fin["date_seance"],
        "cours_debut": p0,
        "cours_fin": p1,
        "variation_fcfa": p1 - p0,
        "variation_pct": round((p1 - p0) / p0 * 100, 2) if p0 else None,
        "nb_seances": len(rows),
    }


def db_stats(db_path: Path | str = DEFAULT_DB) -> dict:
    """État de la base : profondeur d'historique et volumétrie."""
    with _connect(db_path) as conn:
        c = conn.execute(
            "SELECT COUNT(*) n, MIN(date_seance) mn, MAX(date_seance) mx,"
            " COUNT(DISTINCT date_seance) j, COUNT(DISTINCT symbole) s"
            " FROM cours_historique"
        ).fetchone()
        d = conn.execute("SELECT COUNT(*) n FROM dividendes_historique").fetchone()
    return {
        "lignes_cours": c["n"],
        "premiere_seance": c["mn"],
        "derniere_seance": c["mx"],
        "nb_seances_couvertes": c["j"],
        "nb_titres_suivis": c["s"],
        "annonces_dividendes": d["n"],
    }
