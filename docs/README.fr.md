# brvm-mcp

[![smithery badge](https://smithery.ai/badge/sotechdi/brvm-mcp)](https://smithery.ai/server/sotechdi/brvm-mcp)
[![M8ven Live Monitored](https://m8ven.ai/badge/mcp/sotechdi-brvm-mcp-1iuft0)](https://m8ven.ai/mcp/sotechdi-brvm-mcp-1iuft0)
[![Tarifs](https://img.shields.io/badge/Tarifs-Gratuit%20%2F%20Pro%20%249%2Fmois-C9A227?style=flat)](https://sotechdi.github.io/brvm-mcp/)

*🇬🇧 [English version](../README.md)*

Serveur MCP donnant aux assistants IA l'accès aux données publiques de la **BRVM** — la Bourse Régionale des Valeurs Mobilières, place commune aux 8 pays de l'UEMOA (Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, Mali, Niger, Sénégal, Togo).

La BRVM ne publie aucune API publique. Ce serveur agrège **4 sources de données** en **18 outils MCP**, afin que n'importe quel assistant IA (Claude Desktop, Claude Code, etc.) puisse interroger les cours du jour, les fondamentaux, les dividendes, les volumes et les indices sectoriels.

> **Avertissement :** information et analyse uniquement. Ne constitue pas un conseil en investissement (activité réglementée par l'AMF-UMOA). Les performances passées ne préjugent pas des performances futures.

---

## 18 outils

### Données officielles — brvm.org

| Outil | Description |
|-------|-------------|
| `brvm_market_summary` | Vue d'ensemble : indices BRVM-C, BRVM-30, BRVM-Prestige, capitalisation, transactions, plus fortes hausses et baisses |
| `brvm_quotes` | Cours (FCFA) et variation en % — les 47 titres ou un seul |
| `brvm_list_companies` | Sociétés cotées, filtrables par pays |
| `brvm_company_details` | Fiche société + liens vers les PDF (rapports annuels, BOC) |
| `brvm_dividends` | Dividendes à venir : émetteur, ticker, date, montant par action |
| `brvm_dividend_yield` | Rendement du dividende, du plus élevé au plus faible — la BRVM est avant tout un marché de rendement |
| `brvm_price_history` | Historique des cours depuis la base SQLite locale (nécessite `snapshot.py`) |
| `brvm_performance` | Performance d'un titre sur la période historisée |
| `brvm_history_status` | Profondeur de la base : première/dernière séance, titres suivis |
| `brvm_fundamentals` | PER, BPA, capitalisation depuis un PDF (BOC ou rapport annuel) |
| `brvm_diagnose_pdf` | Diagnostic de structure d'un PDF, pour déboguer l'extraction |

### Sources complémentaires

| Outil | Source | Apport par rapport à brvm.org |
|-------|--------|-------------------------------|
| `brvm_volumes` | AFX Kwayisi | Volumes d'échange (absents de brvm.org) |
| `brvm_fondamentaux_ticker` | AFX Kwayisi | PER, BPA, rendement par ticker — sans PDF |
| `brvm_historique_avec_volumes` | AFX Kwayisi | 10 dernières séances avec volumes |
| `brvm_indices_sectoriels` | AFX Kwayisi | Indices sectoriels : énergie, services financiers, services publics (jour / 1 sem. / depuis janvier) |
| `brvm_cotations_enrichies` | Rich Bourse | Cours de veille + capitalisation par titre |
| `brvm_ohlc` | Sika Finance | Ouverture / Haut / Bas / Clôture + volumes |
| `brvm_dividendes_sikafinance` | Sika Finance | Recoupement des annonces de dividendes |

---

## Démarrage rapide

### Claude Desktop

Ajouter dans `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "brvm": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/sotechdi/brvm-mcp", "brvm-mcp"]
    }
  }
}
```

Redémarrer Claude Desktop, puis demander : *« Quelles sont les actions de la BRVM avec le meilleur rendement du dividende ? »*

**Emplacement du fichier de configuration :**
- macOS : `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows : `%APPDATA%\Claude\claude_desktop_config.json`
- Windows (Store) : `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`

### Claude Code

```bash
claude mcp add brvm -- uvx --from git+https://github.com/sotechdi/brvm-mcp brvm-mcp
```

### Installation manuelle (pip)

```bash
git clone https://github.com/sotechdi/brvm-mcp.git
cd brvm-mcp
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

---

## Mode HTTP / Docker

Pour un déploiement réseau ou l'intégration de clients MCP non-stdio :

```bash
docker compose up -d
```

Expose un point d'accès MCP `streamable-http` sur le port 8000. Utiliser `MCP_TRANSPORT=sse` pour les clients SSE historiques.

---

## Données historiques

brvm.org n'expose que la séance en cours. Pour construire des analyses de tendance, lancer `snapshot.py` chaque jour après la clôture (fixing BRVM vers 10 h 45 GMT) :

```bash
python snapshot.py          # capture la séance du jour (idempotent)
python snapshot.py --stats  # affiche la couverture de la base
```

Automatisation avec cron (jours ouvrés à 12 h GMT) :

```cron
0 12 * * 1-5  cd /chemin/vers/brvm-mcp && .venv/bin/python snapshot.py >> snapshot.log 2>&1
```

---

## Agent LLM & conformité réglementaire

Au-delà de l'accès aux données, le dépôt embarque un agent ReAct (LangGraph) qui exploite les 18 outils MCP et répond aux questions de marché en langage naturel.

**La conformité est intégrée à l'architecture.** Publier des recommandations d'investissement dans l'espace UEMOA est une activité réglementée, nécessitant un agrément CIB délivré par l'AMF-UMOA. Plutôt que de s'en remettre aux seules consignes de prompt, chaque réponse passe par un **linter éditorial** qui bloque le vocabulaire prescriptif — *acheter*, *vendre*, *nous recommandons*, *objectif de cours*, *sous-évalué* — avant restitution. Un texte non conforme lève `EditorialViolation` : il est **rejeté, jamais réécrit en silence** — réécrire masquerait le dérapage au lieu de le signaler.

Le linter cible des *tournures* prescriptives, pas des mots isolés. « La société a vendu sa filiale » est un événement social et passe ; « vendez SONATEL » est refusé. La comparaison est de plus **insensible aux accents** : « sous-évalué » et « sous-evalue » sont bloqués tous les deux, car un garde-fou qu'une lettre manquante contourne ne protège de rien. Ce sont ces deux distinctions qui le rendent utilisable sur de vrais bulletins.

```bash
pytest tests/test_editorial.py   # 23 textes prescriptifs bloqués, 14 textes factuels préservés
```

Les réponses restent ainsi dans le registre du fait : cours, rendements, volumes, événements sociaux. Ni conseil, ni prévision.

---

## Architecture

```
brvm-mcp/
├── server.py               # Serveur FastMCP — 18 outils, transports stdio/HTTP/SSE
├── snapshot.py             # Capture quotidienne pour la base historique
├── brvm_scraper/
│   ├── client.py           # Session HTTP, cache TTL (15 min), retry/backoff
│   ├── quotes.py           # Cours, indices, activité du marché (brvm.org)
│   ├── companies.py        # Sociétés cotées avec filtre par pays
│   ├── dividends.py        # Dividendes + calcul du rendement
│   ├── afx_kwayisi.py      # Volumes, fondamentaux, indices sectoriels (AFX)
│   ├── richbourse.py       # Cours de veille, capitalisation (Rich Bourse)
│   ├── sikafinance.py      # OHLC, dividendes (Sika Finance)
│   ├── storage.py          # Historisation SQLite (UPSERT, stats, performance)
│   └── fundamentals.py     # Extraction PER / BPA depuis PDF (pdfplumber)
├── agent/
│   ├── graph.py            # Agent ReAct LangGraph sur les outils MCP
│   ├── tools.py            # Enveloppes LangChain — les 18 outils
│   ├── prompts.py          # Prompt système — rôle analytique, jamais consultatif
│   ├── editorial.py        # Blocage du vocabulaire prescriptif (garde-fou réglementaire)
│   └── cli.py              # Interface en ligne de commande
└── tests/
    ├── fixture_home.html   # HTML brvm.org capturé pour les tests hors ligne
    ├── test_parsers.py     # Analyse des cours / dividendes
    ├── test_storage.py     # Stockage SQLite
    ├── test_agent_smoke.py # Test de fumée de l'agent
    └── test_editorial.py   # Linter éditorial — blocage + garde anti-faux-positifs
```

**Notes techniques :**
- Regex sur le texte des pages, pas de sélecteurs CSS — plus résistant aux changements de thème
- Cache TTL de 15 minutes — la BRVM ne fait qu'un fixing par jour (vers 10 h 45 GMT), inutile de solliciter les sources en continu
- User-Agent identifiable + backoff exponentiel — respect des infrastructures publiques

---

## Tarifs

**[→ sotechdi.github.io/brvm-mcp](https://sotechdi.github.io/brvm-mcp/)**

| Formule | Prix | Appels |
|---------|------|--------|
| **Gratuit** | 0 $ | 25/jour en HTTP (illimité en mode stdio local) |
| **Pro** | 9 $/mois | Illimité + clé API personnelle |
| **Business** | 29 $/mois | Illimité + 5 clés API + support prioritaire |

Paiement : Orange Money, Moov, PayPal, virement bancaire — [contact@sotechdi.com](mailto:contact@sotechdi.com?subject=brvm-mcp%20Pro)

---

## Communauté

Questions, retours ou idées ? Ouvrez une [discussion GitHub](https://github.com/sotechdi/brvm-mcp/discussions) — ou rejoignez le groupe WhatsApp francophone (Burkina Faso, Côte d'Ivoire, Sénégal…) : **[bientôt disponible]**

Si ce serveur vous est utile, une ⭐ sur GitHub aide les autres à le découvrir — merci !

---

## Licence

MIT — © 2026 Christian Dondire
