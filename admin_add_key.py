#!/usr/bin/env python3
"""
admin_add_key.py — Gestion des clés API brvm-mcp

Usage:
    python admin_add_key.py add --email client@example.com --tier pro [--name "Jean Dupont"]
    python admin_add_key.py list
    python admin_add_key.py revoke --email client@example.com

Workflow complet :
    1. Le client remplit le formulaire sur sotechdi.github.io/brvm-mcp/
    2. Vous recevez un email de notification
    3. Encaissez le paiement (Orange Money / PayPal / virement)
    4. Exécutez : python admin_add_key.py add --email X --tier pro --name "Y"
    5. Copiez la valeur BRVM_API_KEYS dans Railway Dashboard → Variables
    6. Envoyez l'email généré automatiquement au client
"""

import argparse
import json
import os
import uuid
from datetime import date
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent
ENV_FILE = ROOT / ".env"
KEY_VAR  = "BRVM_API_KEYS"

DIVIDER = "━" * 62


# ── Helpers ────────────────────────────────────────────────────────────────

def _read_env_var(var: str) -> str:
    """Lit une variable d'environnement injectée par Railway ou depuis .env."""
    val = os.getenv(var, "")
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{var}=") and not line.startswith("#"):
                return line[len(f"{var}="):].strip().strip('"').strip("'")
    return ""


def load_keys() -> dict:
    """Charge le dictionnaire des clés API actuelles."""
    raw = _read_env_var(KEY_VAR)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  ⚠  {KEY_VAR} contient du JSON invalide — dictionnaire vide utilisé.")
        return {}


def _railway_url() -> str:
    return _read_env_var("RAILWAY_SERVICE_URL") or "https://<votre-app>.up.railway.app"


def _print_deployment(keys: dict) -> None:
    """Affiche les instructions pour déployer la nouvelle valeur sur Railway."""
    new_json = json.dumps(keys, ensure_ascii=False, separators=(",", ":"))

    print()
    print(DIVIDER)
    print("  ÉTAPE 1 — Coller dans Railway Dashboard")
    print(DIVIDER)
    print()
    print("  URL : https://railway.app  → Projet → Service → Variables")
    print(f"  Variable : {KEY_VAR}")
    print(f"  Valeur   :")
    print()
    print(f"  {new_json}")
    print()
    print(DIVIDER)
    print("  ÉTAPE 1 (alt) — Commande Railway CLI")
    print(DIVIDER)
    print()
    print(f"  railway variables set {KEY_VAR}='{new_json}'")
    print()
    print("  (Railway redémarre le service automatiquement)")
    print(DIVIDER)
    print()


def _print_email(key: str, email: str, tier: str, name: str = "") -> None:
    """Génère le template d'email à envoyer au client."""
    greeting  = f"Bonjour{f' {name}' if name else ''},"
    tier_label = "Pro ($9/mois)" if tier == "pro" else "Business ($29/mois)"
    mcp_url    = f"{_railway_url().rstrip('/')}/mcp?api_key={key}"

    print(DIVIDER)
    print("  ÉTAPE 2 — Email à envoyer au client")
    print(DIVIDER)
    print()
    print(f"  À      : {email}")
    print(f"  Objet  : Votre clé API brvm-mcp {tier_label}")
    print()
    print(f"""\
{greeting}

Merci pour votre abonnement brvm-mcp {tier_label} !

Voici votre clé API personnelle :

    {key}

─── Configuration Claude Desktop ───────────────────────────────

Fichier : claude_desktop_config.json
  Windows : %APPDATA%\\Claude\\claude_desktop_config.json
  macOS   : ~/Library/Application Support/Claude/claude_desktop_config.json

{{
  "mcpServers": {{
    "brvm": {{
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "{mcp_url}"]
    }}
  }}
}}

─── Configuration Claude Code (terminal) ───────────────────────

claude mcp add brvm -- npx -y mcp-remote@latest "{mcp_url}"

────────────────────────────────────────────────────────────────

Votre clé est active immédiatement — plus de limite d'appels.
En cas de question, répondez simplement à cet email.

Bonne analyse !
Christian Dondire — SOTECHDI
contact@sotechdi.com
https://sotechdi.github.io/brvm-mcp/\
""")
    print()
    print(DIVIDER)
    print()


# ── Commandes ──────────────────────────────────────────────────────────────

def cmd_add(args):
    keys = load_keys()

    # Vérifier si l'email a déjà une clé
    existing = [(k, v) for k, v in keys.items() if v.get("email") == args.email]
    if existing and not args.force:
        print(f"\n  ⚠  Cet email a déjà une clé active : {existing[0][0]}")
        print("     Utilisez --force pour en générer une supplémentaire.\n")
        return

    new_key = str(uuid.uuid4())
    today   = str(date.today())

    keys[new_key] = {
        "tier":    args.tier,
        "email":   args.email,
        "name":    args.name or "",
        "created": today,
    }

    print()
    print(f"  ✅ Clé générée")
    print(f"     UUID  : {new_key}")
    print(f"     Email : {args.email}")
    print(f"     Tier  : {args.tier}")
    print(f"     Date  : {today}")

    _print_deployment(keys)
    _print_email(new_key, args.email, args.tier, args.name or "")


def cmd_list(args):
    keys = load_keys()
    if not keys:
        print("\n  Aucune clé API configurée.\n")
        return

    print(f"\n  {len(keys)} clé(s) API active(s):\n")
    hdr = f"  {'UUID':<38}  {'Tier':<10}  {'Email':<30}  {'Nom':<20}  Créée"
    print(hdr)
    print("  " + "─" * 110)
    for key, info in keys.items():
        print(
            f"  {key:<38}  {info.get('tier','?'):<10}  "
            f"{info.get('email','?'):<30}  {info.get('name',''):<20}  "
            f"{info.get('created','?')}"
        )
    print()


def cmd_revoke(args):
    keys  = load_keys()
    query = args.email
    found = [k for k, v in keys.items() if v.get("email") == query or k == query]

    if not found:
        print(f"\n  ⚠  Aucune clé trouvée pour : {query}\n")
        return

    for k in found:
        info = keys.pop(k)
        print(f"\n  ✅ Clé révoquée : {k}  ({info.get('email', '?')})")

    _print_deployment(keys)


# ── Point d'entrée ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gestion des clés API brvm-mcp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python admin_add_key.py add --email jean@example.com --tier pro --name "Jean Dupont"
  python admin_add_key.py add --email sgi@example.com --tier business --name "SGI Burkina"
  python admin_add_key.py list
  python admin_add_key.py revoke --email jean@example.com
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="Créer une nouvelle clé API")
    p.add_argument("--email",  required=True, help="Email du client")
    p.add_argument("--tier",   required=True, choices=["pro", "business"])
    p.add_argument("--name",   default="", help="Nom du client (optionnel)")
    p.add_argument("--force",  action="store_true", help="Créer même si email déjà présent")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="Lister les clés actives")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("revoke", help="Révoquer une clé")
    p.add_argument("--email", required=True, help="Email du client ou UUID de la clé")
    p.set_defaults(func=cmd_revoke)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
