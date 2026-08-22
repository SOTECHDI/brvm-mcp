"""
Linter éditorial : garde-fou de conformité AMF-UMOA.

Le prompt système (voir prompts.py) demande à l'agent de rester factuel, mais une
instruction de prompt n'est pas une garantie : un LLM peut déraper. Ce module est
le contrôle *déterministe* qui s'exécute APRÈS génération, sur le texte final.

Principe : publier une recommandation d'investissement dans l'UEMOA est une
activité réglementée (agrément CIB délivré par l'AMF-UMOA). Un texte qui contient
du vocabulaire prescriptif est donc REJETÉ, jamais réécrit silencieusement —
réécrire masquerait le dérapage au lieu de le signaler.

Choix de conception important : on cible des TOURNURES prescriptives, pas des mots
isolés. Bloquer « vendre » casserait un bulletin factuel légitime comme « la
société a vendu sa filiale » (événement d'entreprise, information licite). On
cherche l'injonction (« achetez »), le conseil (« nous recommandons »), la
valorisation subjective (« sous-évalué ») et la prévision (« objectif de cours »).
"""

import re

# Chaque entrée : (motif, libellé lisible expliquant pourquoi c'est bloqué).
# re.IGNORECASE est appliqué à la compilation ; les motifs gèrent l'apostrophe
# droite (') et typographique (’), fréquentes dans du texte généré.
_MOTIFS = [
    # --- Injonctions directes (français) ---
    (r"\bachet(?:ez|ons)\b", "injonction d'achat"),
    (r"\bvend(?:ez|ons)\b", "injonction de vente"),
    (r"\b(?:positionnez|misez|profitez)[- ]?(?:vous)?\b", "incitation à l'action"),
    (r"\bn['’]attendez\s+pas\b", "incitation à l'action"),
    (r"\b(?:à|a)\s+(?:acheter|vendre)\b", "qualification « à acheter/vendre »"),
    (r"\bil\s+faut\s+(?:acheter|vendre|investir)\b", "injonction d'investissement"),
    (r"\bvous\s+devriez\s+(?:acheter|vendre|investir)\b", "injonction d'investissement"),
    # --- Conseil explicite (français) ---
    (r"\b(?:je\s+recommande|nous\s+recommandons)\b", "recommandation explicite"),
    (r"\b(?:je\s+vous\s+conseille|nous\s+conseillons)\b", "conseil explicite"),
    (r"\b(?:recommandation|conseil)\s+d['’]achat\b", "recommandation d'achat"),
    (r"\b(?:notre\s+recommandation|notre\s+conseil)\b", "conseil explicite"),
    (r"\bopportunit[ée]s?\s+d['’]achat\b", "qualification en opportunité d'achat"),
    # « à l'achat » seul est ambigu : « 12 000 titres à l'achat » est une donnée
    # de carnet d'ordres, parfaitement factuelle. On n'attrape donc que les
    # tournures où l'expression sert d'opinion.
    (r"\b(?:pass(?:er|ons|ez|e|[ée]e?s?)|opinion|recommandation|conseil|valeur)\s+"
     r"(?:à|a)\s+(?:l['’]achat|la\s+vente)\b", "opinion « à l'achat/à la vente »"),
    # --- Valorisation subjective (français) ---
    (r"\bsous[-\s]?(?:évalu|valoris)[ée]e?s?\b", "jugement de valorisation"),
    (r"\bsur[-\s]?(?:évalu|valoris)[ée]e?s?\b", "jugement de valorisation"),
    (r"\bvaleur\s+s[ûu]re\b", "garantie implicite de performance"),
    (r"\bplacement\s+id[ée]al\b", "garantie implicite de performance"),
    (r"\b(?:p[ée]pite|incontournable|belle\s+affaire)\b", "jugement de valeur sur un titre"),
    (r"\bprometteu(?:r|se)s?\b", "jugement de valeur sur un titre"),
    # --- Prescription déguisée (français) ---
    (r"\b(?:à|a)\s+surveiller\b", "prescription déguisée"),
    (r"\b(?:à|a)\s+suivre\s+de\s+pr[èe]s\b", "prescription déguisée"),
    (r"\bpoint\s+d['’]entr[ée]e\b", "prescription déguisée"),
    # --- Prévision / objectif de cours (français) ---
    (r"\bobjectif\s+de\s+cours\b", "objectif de cours (prévision)"),
    (r"\bpotentiel\s+de\s+(?:hausse|baisse)\b", "prévision de performance"),
    (r"\bva\s+(?:monter|baisser|grimper|s['’]envoler)\b", "prévision de performance"),
    (r"\b(?:devrait|pourrait)\s+(?:progresser|reculer|atteindre|monter|baisser)\b",
     "prévision de performance"),
    (r"\b(?:s['’]envolera|chutera)\b", "prévision de performance"),
    # --- Équivalents anglais ---
    # L'impératif anglais est le verbe nu : « Buy SONATEL ». On ne peut donc pas
    # bloquer « buy » partout — « buy orders reached 12,000 » est une donnée de
    # carnet d'ordres, et « sell-side analysts » une catégorie de métier. On cible
    # l'impératif en tête de phrase, en excluant ces emplois factuels.
    (r"(?:^|[.!?;:\n]\s*)(?:buy|sell)\b"
     r"(?!\s*[-–]?\s*(?:orders?|side|volume|pressure|price|ratio)\b)",
     "injonction d'achat/vente"),
    (r"\btime\s+to\s+(?:buy|sell)\b", "injonction d'achat/vente"),
    (r"\bworth\s+(?:buying|selling)\b", "jugement de valeur sur un titre"),
    (r"\bstrong\s+buy\b", "notation prescriptive (strong buy)"),
    (r"\b(?:buy|sell)\s+(?:rating|recommendation|signal)\b", "notation prescriptive"),
    (r"\bprice\s+target\b", "objectif de cours (prévision)"),
    (r"\b(?:under|over)valued\b", "jugement de valorisation"),
    (r"\bwe\s+recommend\b", "recommandation explicite"),
    (r"\byou\s+should\s+(?:buy|sell|invest)\b", "injonction d'investissement"),
    (r"\bmust[-\s]buy\b", "injonction d'achat"),
]

_MOTIFS_COMPILES = [(re.compile(m, re.IGNORECASE), libelle) for m, libelle in _MOTIFS]

# Nombre de caractères de contexte affichés autour d'une infraction, pour que
# l'utilisateur retrouve le passage fautif sans relire tout le bulletin.
_CONTEXTE = 40


class EditorialViolation(Exception):
    """
    Levée quand le texte généré contient du vocabulaire prescriptif.

    L'attribut `violations` porte le détail (terme, motif du blocage, extrait),
    ce qui permet à un appelant de journaliser ou de réafficher proprement.
    """

    def __init__(self, violations: list[dict]):
        self.violations = violations
        details = "\n".join(
            f"  - « {v['terme']} » ({v['raison']}) … {v['extrait']} …" for v in violations
        )
        super().__init__(
            "Texte rejeté : vocabulaire prescriptif détecté "
            f"({len(violations)} infraction(s)).\n{details}\n"
            "Publier un conseil en investissement dans l'UEMOA exige un agrément AMF-UMOA."
        )


def check(texte: str) -> list[dict]:
    """
    Inspecte un texte et renvoie la liste des infractions trouvées.

    Ne lève rien : utile pour tester, journaliser ou afficher un avertissement
    sans interrompre le flux. Renvoie une liste vide si le texte est conforme.
    """
    if not texte:
        return []

    violations = []
    for motif, raison in _MOTIFS_COMPILES:
        for trouve in motif.finditer(texte):
            debut = max(0, trouve.start() - _CONTEXTE)
            fin = min(len(texte), trouve.end() + _CONTEXTE)
            violations.append({
                "terme": trouve.group(0),
                "raison": raison,
                "position": trouve.start(),
                "extrait": texte[debut:fin].replace("\n", " ").strip(),
            })

    # Tri par position : l'utilisateur lit les infractions dans l'ordre du texte.
    violations.sort(key=lambda v: v["position"])
    return violations


def enforce(texte: str) -> str:
    """
    Renvoie le texte s'il est conforme, sinon lève EditorialViolation.

    C'est le point d'entrée utilisé par le pipeline de génération : un texte non
    conforme n'est pas publié, et l'erreur explique précisément ce qui bloque.
    """
    violations = check(texte)
    if violations:
        raise EditorialViolation(violations)
    return texte
