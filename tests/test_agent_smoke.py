"""
Test de fumée de l'agent. Se contente de vérifier, SI les dépendances LangGraph
sont installées, que les outils sont bien enregistrés et que l'agent se construit.
Skippé proprement si langgraph absent (ex: environnement scraper-seul).
"""
import sys, pathlib, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from langchain_core.tools import BaseTool  # noqa
    import langgraph  # noqa
except ImportError:
    print("SKIP: LangGraph non installé (pip install -r requirements-agent.txt).")
    sys.exit(0)

from agent.tools import TOOLS

# 1. Les outils sont bien des outils LangChain avec nom + description
noms = [t.name for t in TOOLS]
print(f"[outils] {len(TOOLS)} outils enregistrés : {', '.join(noms)}")
assert len(TOOLS) == 18, f"parité avec les 18 outils MCP attendue, obtenu {len(TOOLS)}"
for t in TOOLS:
    assert t.description and len(t.description) > 20, f"{t.name} : description trop courte"

# 2. L'agent se construit SI la clé API est présente
if os.environ.get("ANTHROPIC_API_KEY"):
    from agent.graph import build_agent
    agent = build_agent()
    print("[agent] construit avec succès")
else:
    print("[agent] construction non testée (ANTHROPIC_API_KEY absente) — OK")

print(">>> SMOKE TEST AGENT OK <<<")
