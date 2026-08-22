# brvm-mcp

[![smithery badge](https://smithery.ai/badge/sotechdi/brvm-mcp)](https://smithery.ai/server/sotechdi/brvm-mcp)
[![M8ven Live Monitored](https://m8ven.ai/badge/mcp/sotechdi-brvm-mcp-1iuft0)](https://m8ven.ai/mcp/sotechdi-brvm-mcp-1iuft0)
[![Pricing](https://img.shields.io/badge/Pricing-Free%20%2F%20Pro%20%249%2Fmo-C9A227?style=flat)](https://sotechdi.github.io/brvm-mcp/)

MCP server giving AI assistants access to **BRVM** public data — the West African regional stock exchange serving 8 UEMOA countries (Benin, Burkina Faso, Côte d'Ivoire, Guinea-Bissau, Mali, Niger, Senegal, Togo).

The BRVM publishes no public API. This server aggregates **4 data sources** into **18 MCP tools** so any AI assistant (Claude Desktop, Claude Code, etc.) can query real-time market data, fundamentals, dividends, volumes, and sector indices.

> **Disclaimer:** For information and analysis only. Does not constitute investment advice (regulated activity under AMF-UMOA). Past performance does not guarantee future results.

---

## 18 tools

### Official data — brvm.org

| Tool | Description |
|------|-------------|
| `brvm_market_summary` | Market overview: BRVM-C, BRVM-30, BRVM-Prestige indices, market cap, transactions, top/worst movers |
| `brvm_quotes` | Prices (FCFA) and % change — all 47 tickers or a specific one |
| `brvm_list_companies` | Listed companies, filterable by country |
| `brvm_company_details` | Company profile + PDF document links (annual reports, BOC) |
| `brvm_dividends` | Upcoming dividend payments: issuer, ticker, date, amount per share |
| `brvm_dividend_yield` | Dividend yield ranked highest first — the BRVM is primarily a yield market |
| `brvm_price_history` | Historical prices from local SQLite database (requires `snapshot.py`) |
| `brvm_performance` | Price performance over the tracked period |
| `brvm_history_status` | Database depth: first/last session, tickers tracked |
| `brvm_fundamentals` | P/E ratio, EPS, market cap from BOC PDF or annual report |
| `brvm_diagnose_pdf` | PDF structure diagnostic for troubleshooting extraction |

### Supplementary sources

| Tool | Source | Added value vs brvm.org |
|------|--------|------------------------|
| `brvm_volumes` | AFX Kwayisi | Trading volumes (absent from brvm.org) |
| `brvm_fondamentaux_ticker` | AFX Kwayisi | P/E, EPS, dividend yield per ticker — no PDF needed |
| `brvm_historique_avec_volumes` | AFX Kwayisi | Last 10 sessions with volumes |
| `brvm_indices_sectoriels` | AFX Kwayisi | Sector indices: Energy, Financial Services, Public Utilities (day / 1WK / YTD) |
| `brvm_cotations_enrichies` | Rich Bourse | Previous close + market cap per ticker |
| `brvm_ohlc` | Sika Finance | Open / High / Low / Close + volumes |
| `brvm_dividendes_sikafinance` | Sika Finance | Cross-check dividend announcements |

---

## Quick start

### Claude Desktop

Add to `claude_desktop_config.json`:

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

Restart Claude Desktop. Then ask: *"What are the BRVM stocks with the highest dividend yield?"*

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Windows (Store): `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`

### Claude Code

```bash
claude mcp add brvm -- uvx --from git+https://github.com/sotechdi/brvm-mcp brvm-mcp
```

### Manual install (pip)

```bash
git clone https://github.com/sotechdi/brvm-mcp.git
cd brvm-mcp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

---

## HTTP / Docker mode

For network deployment or integration with non-stdio MCP clients:

```bash
docker compose up -d
```

Exposes a `streamable-http` MCP endpoint on port 8000. Set `MCP_TRANSPORT=sse` for legacy SSE clients.

---

## Historical data

brvm.org only exposes the current session. To build trend analysis, run `snapshot.py` daily after market close (BRVM fixing ~10:45 GMT):

```bash
python snapshot.py          # capture today's session (idempotent)
python snapshot.py --stats  # show database coverage
```

Automate with cron (weekdays at 12:00 GMT):

```cron
0 12 * * 1-5  cd /path/to/brvm-mcp && .venv/bin/python snapshot.py >> snapshot.log 2>&1
```

---

## LLM agent & regulatory compliance

Beyond raw data access, the repository ships a ReAct agent (LangGraph) that
consumes the 18 MCP tools and answers market questions in plain language.

**Compliance by design.** Publishing investment recommendations in the UEMOA
zone is a regulated activity requiring a CIB licence from the AMF-UMOA. Rather
than relying on prompt instructions alone, every answer passes through an
**editorial linter** that blocks prescriptive vocabulary — *buy*, *sell*,
*we recommend*, *price target*, *undervalued* — before it is returned. Output
that fails the check raises `EditorialViolation` and is **rejected, not
silently rewritten**: rewriting would hide the drift instead of surfacing it.

The linter matches prescriptive *constructions*, not isolated words. "The
company sold its subsidiary" is a corporate event and passes; "sell SONATEL"
does not. This distinction is what keeps the guardrail usable on real bulletins.

```bash
pytest tests/test_editorial.py   # 18 prescriptive samples blocked, 10 factual ones passed
```

Answers therefore stay within factual reporting: prices, yields, volumes,
corporate events. No advice, no forecasts.

---

## Architecture

```
brvm-mcp/
├── server.py               # FastMCP server — 18 tools, stdio/HTTP/SSE transports
├── snapshot.py             # Daily snapshot for historical database
├── brvm_scraper/
│   ├── client.py           # HTTP session, TTL cache (15 min), retry/backoff
│   ├── quotes.py           # Prices, indices, market activity (brvm.org)
│   ├── companies.py        # Listed companies with country filter
│   ├── dividends.py        # Dividends + yield calculation
│   ├── afx_kwayisi.py      # Volumes, fundamentals, sector indices (AFX)
│   ├── richbourse.py       # Previous close, market cap (Rich Bourse)
│   ├── sikafinance.py      # OHLC, dividends (Sika Finance)
│   ├── storage.py          # SQLite historization (UPSERT, stats, performance)
│   └── fundamentals.py     # P/E / EPS extraction from PDF (pdfplumber)
├── agent/
│   ├── graph.py            # LangGraph ReAct agent over the MCP tools
│   ├── tools.py            # LangChain wrappers — all 18 tools
│   ├── prompts.py          # System prompt — analytical role, never advisory
│   ├── editorial.py        # Prescriptive-vocabulary blocker (regulatory guardrail)
│   └── cli.py              # Interactive CLI
└── tests/
    ├── fixture_home.html   # Captured brvm.org HTML for offline tests
    ├── test_parsers.py     # Quote / dividend parsing
    ├── test_storage.py     # SQLite storage
    ├── test_agent_smoke.py # Agent smoke test
    └── test_editorial.py   # Editorial linter — blocking + false-positive guard
```

**Technical notes:**
- Regex on page text, not CSS selectors — more resilient to theme changes
- 15-minute TTL cache — BRVM runs a single daily fixing (~10:45 GMT), no need to hammer sources
- Identifiable User-Agent + exponential backoff — respectful of public infrastructure

---

## Pricing

**[→ sotechdi.github.io/brvm-mcp](https://sotechdi.github.io/brvm-mcp/)**

| Tier | Price | Calls |
|------|-------|-------|
| **Free** | $0 | 25/day via HTTP (unlimited in local stdio mode) |
| **Pro** | $9/month | Unlimited + personal API key |
| **Business** | $29/month | Unlimited + 5 API keys + priority support |

Payment: Orange Money, Moov, PayPal, bank transfer — [contact@sotechdi.com](mailto:contact@sotechdi.com?subject=brvm-mcp%20Pro)

---

## Community

Questions, feedback, or ideas? Open a [GitHub Discussion](https://github.com/sotechdi/brvm-mcp/discussions) — or join the WhatsApp group for French-speaking users (Burkina Faso, Côte d'Ivoire, Sénégal…): **[coming soon]**

If this server is useful to you, a ⭐ on GitHub helps others find it — thank you!

---

## License

MIT — © 2026 Christian Dondire
