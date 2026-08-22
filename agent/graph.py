"""
Agent BRVM construit avec LangGraph.

Architecture : agent ReAct (Reasoning + Acting). Le LLM raisonne, appelle les
outils de données quand nécessaire, observe les résultats, puis synthétise une
réponse. LangGraph gère la boucle et l'état (historique de conversation).

On utilise create_react_agent (pré-construit, robuste) plutôt qu'un graphe
manuel : c'est le pattern recommandé pour un agent outillé, et il reste
extensible (checkpointing, mémoire, sous-graphes) si besoin plus tard.
"""

import os

# Chargement optionnel du fichier .env (si python-dotenv est installé).
# Permet de mettre ANTHROPIC_API_KEY dans un .env plutôt que de l'exporter
# à chaque session. Sans dotenv, on retombe sur les variables d'environnement.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from .editorial import enforce
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS

DEFAULT_MODEL = "claude-sonnet-4-6"


def build_agent(model: str = DEFAULT_MODEL, temperature: float = 0.2):
    """
    Construit l'agent BRVM prêt à l'emploi.

    Nécessite la variable d'environnement ANTHROPIC_API_KEY.
    Température basse (0.2) : on veut de la rigueur factuelle, pas de créativité.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise EnvironmentError(
            "ANTHROPIC_API_KEY manquante. Définissez-la avant de lancer l'agent :\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )

    llm = ChatAnthropic(model=model, temperature=temperature, max_tokens=2048)

    # MemorySaver : conserve l'historique par 'thread_id' entre les tours.
    checkpointer = MemorySaver()

    agent = create_react_agent(
        llm,
        tools=TOOLS,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
    return agent


def ask(
    agent,
    question: str,
    thread_id: str = "default",
    enforce_editorial: bool = True,
) -> str:
    """
    Pose une question à l'agent et renvoie sa réponse texte.
    Le 'thread_id' permet de tenir plusieurs conversations séparées.

    Par défaut, la réponse passe par le linter éditorial (voir editorial.py) :
    un texte contenant du vocabulaire prescriptif lève EditorialViolation plutôt
    que d'être renvoyé. Le prompt système seul ne suffit pas comme garantie de
    conformité AMF-UMOA ; ce contrôle est déterministe.
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
    )
    # Le dernier message est la réponse de l'agent.
    reponse = result["messages"][-1].content
    return enforce(reponse) if enforce_editorial else reponse
