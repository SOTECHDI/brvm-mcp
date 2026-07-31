#!/usr/bin/env python3
"""
Interface en ligne de commande pour discuter avec l'agent BRVM.

Usage :
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m agent.cli

    # ou une question unique :
    python -m agent.cli "Quelles valeurs ont le meilleur rendement du dividende ?"
"""

import sys

from .graph import build_agent, ask


BANNIERE = """\
╭──────────────────────────────────────────────────────────╮
│  Agent d'analyse BRVM  ·  outil d'information             │
│  Pas un conseil en investissement (réglementé AMF-UMOA)  │
╰──────────────────────────────────────────────────────────╯
Tapez votre question. 'quit' ou Ctrl-C pour sortir.
"""


def main() -> int:
    try:
        agent = build_agent()
    except EnvironmentError as e:
        print(e, file=sys.stderr)
        return 1

    # Mode question unique (argument en ligne de commande)
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(ask(agent, question))
        return 0

    # Mode interactif
    print(BANNIERE)
    while True:
        try:
            q = input("\n\033[1mVous ›\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nÀ bientôt !")
            return 0
        if q.lower() in ("quit", "exit", "q"):
            print("À bientôt !")
            return 0
        if not q:
            continue
        try:
            reponse = ask(agent, q)
            print(f"\n\033[36mAgent ›\033[0m {reponse}")
        except Exception as e:
            print(f"\n\033[31mErreur :\033[0m {e}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
