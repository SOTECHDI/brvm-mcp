"""
Rate limiting pour brvm-mcp.

- Mode HTTP (Railway/Smithery) : 25 appels/jour par IP (tier gratuit)
- Mode stdio (local uvx)       : pas de limite (usage local)
- Tier payant                  : clé API valide → pas de limite

Stockage : table `rate_limits` dans brvm_history.db (même base que l'historique).
"""

import contextvars
import json
import sqlite3
from datetime import date
from pathlib import Path

# Variable de contexte : l'identifiant du client courant (IP ou clé API)
# Initialisée par le middleware HTTP, None en mode stdio
current_identifier: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_identifier", default=None
)

DB_PATH = Path(__file__).parent.parent / "brvm_history.db"
FREE_LIMIT = 25  # appels/jour pour le tier gratuit

# Clés API valides → tier payant (pas de limite)
# Format : {"clé": {"tier": "pro"|"business", "email": "..."}}
# À terme : stocké en DB. Pour l'instant : variable d'env BRVM_API_KEYS (JSON)
import os as _os

def _load_paid_keys() -> set:
    raw = _os.getenv("BRVM_API_KEYS", "{}")
    try:
        # Les clés sont stockées comme UUIDs bruts dans BRVM_API_KEYS.
        # Le middleware ASGI les reçoit via ?api_key=UUID et préfixe l'identifiant
        # avec "sk_" → on expose les deux formes pour matcher les deux cas.
        raw_keys = set(json.loads(raw).keys())
        return raw_keys | {f"sk_{k}" for k in raw_keys}
    except Exception:
        return set()


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            identifier TEXT NOT NULL,
            date       TEXT NOT NULL,
            calls      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (identifier, date)
        )
    """)


def check_rate_limit(identifier: str) -> dict:
    """
    Vérifie et incrémente le compteur pour cet identifiant.

    Retourne un dict :
      - allowed   : bool — l'appel est autorisé
      - calls     : int  — nombre d'appels aujourd'hui (après cet appel)
      - remaining : int  — appels restants
      - tier      : "free" | "paid"
    """
    # Clé API payante → pas de limite
    if identifier in _load_paid_keys():
        return {"allowed": True, "calls": 0, "remaining": 999, "tier": "paid"}

    today = str(date.today())

    with sqlite3.connect(DB_PATH) as conn:
        _ensure_table(conn)
        conn.execute("""
            INSERT INTO rate_limits (identifier, date, calls) VALUES (?, ?, 1)
            ON CONFLICT(identifier, date) DO UPDATE SET calls = calls + 1
        """, (identifier, today))
        calls = conn.execute(
            "SELECT calls FROM rate_limits WHERE identifier = ? AND date = ?",
            (identifier, today)
        ).fetchone()[0]

    remaining = max(0, FREE_LIMIT - calls)
    return {
        "allowed": calls <= FREE_LIMIT,
        "calls": calls,
        "remaining": remaining,
        "tier": "free",
    }


def rate_limit_error(remaining_tomorrow: bool = True) -> str:
    """Message d'erreur JSON renvoyé quand la limite est atteinte."""
    return json.dumps({
        "erreur": (
            f"Limite atteinte : {FREE_LIMIT} appels/jour en tier gratuit. "
            "Revenez demain ou passez en Pro ($9/mois) pour un acces illimite. "
            "Details : sotechdi.github.io/brvm-mcp"
        ),
        "tier": "free",
        "limit_per_day": FREE_LIMIT,
        "upgrade_url": "https://sotechdi.github.io/brvm-mcp",
    }, ensure_ascii=False)
