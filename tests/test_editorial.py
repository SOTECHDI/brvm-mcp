"""
Tests du linter éditorial (conformité AMF-UMOA).

Deux exigences opposées, aussi importantes l'une que l'autre :
1. bloquer le vocabulaire prescriptif (sinon le garde-fou ne sert à rien) ;
2. NE PAS bloquer un bulletin factuel légitime (sinon il devient inutilisable —
   un faux positif sur « la société a vendu sa filiale » rendrait la publication
   impossible alors que l'information est parfaitement licite).

Aucune dépendance externe : le linter est du re pur, donc ces tests tournent
partout, même sans LangGraph ni clé API.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent.editorial import check, enforce, EditorialViolation

# --- 1. Textes qui DOIVENT être bloqués -------------------------------------
PRESCRIPTIFS = [
    "Achetez SONATEL avant la fin du mois.",
    "Nous recommandons de renforcer la position sur BOA Bénin.",
    "Le titre est nettement sous-évalué au cours actuel.",
    "Objectif de cours : 18 000 FCFA à douze mois.",
    "SGBCI reste une valeur sûre pour un portefeuille prudent.",
    "C'est une belle opportunité d'achat sur le secteur bancaire.",
    "We recommend increasing exposure to the banking sector.",
    "Strong buy on ETIT at current levels.",
    "The stock appears undervalued versus regional peers.",
    "Price target raised to XOF 12,500.",
    # Vocabulaire aligné sur le linter de la newsletter (brvm/newsletter.py)
    "ONTBF est une pépite du marché burkinabè.",
    "Valeur à surveiller dans les prochaines séances.",
    "Le point d'entrée semble intéressant sous 14 000 FCFA.",
    "Le cours devrait progresser après le détachement du dividende.",
    "Le titre pourrait atteindre 20 000 FCFA d'ici décembre.",
    "Notre recommandation reste inchangée sur le secteur.",
    "Nous passons à l'achat sur SONATEL.",
    "Positionnez-vous avant l'assemblée générale.",
    # Infinitif en tête de phrase = impératif déguisé (style titre)
    "Acheter SONATEL maintenant.",
    "Vendre ETIT avant le détachement du dividende.",
    # SANS ACCENTS : un texte mal accentué ne doit pas contourner le garde-fou
    "Le titre est sous-evalue au cours actuel.",
    "Belle opportunite d'achat sur le secteur bancaire.",
    "Point d'entree interessant sous 14 000 FCFA.",
]

for texte in PRESCRIPTIFS:
    violations = check(texte)
    assert violations, f"NON DÉTECTÉ (faux négatif) : {texte!r}"
    try:
        enforce(texte)
        raise AssertionError(f"enforce() aurait dû lever : {texte!r}")
    except EditorialViolation as e:
        assert e.violations, "EditorialViolation sans détail"

print(f"[prescriptif] {len(PRESCRIPTIFS)}/{len(PRESCRIPTIFS)} textes correctement bloqués")

# --- 2. Textes factuels qui NE DOIVENT PAS être bloqués ---------------------
# Le piège classique : « vendu », « achat », « recommandé » apparaissent
# légitimement dans du reporting factuel.
FACTUELS = [
    "SONATEL a vendu sa filiale malienne pour 12 milliards FCFA.",
    "Le volume échangé s'établit à 45 320 titres, dont 12 000 à l'achat.",
    "La société a annoncé un dividende de 1 250 FCFA par action.",
    "Le cours clôture à 15 400 FCFA, en hausse de 2,3 % sur la séance.",
    "Le PER ressort à 8,4x contre 11,2x pour la moyenne du secteur.",
    "L'indice BRVM Composite progresse de 1,1 % sur la semaine.",
    "Trading volume reached 45,320 shares on the session.",
    "The company sold its Malian subsidiary in Q2.",
    "Le rendement du dividende atteint 7,8 % sur la base du dernier acompte.",
    "Assemblée générale convoquée le 15 juin ; distribution soumise au vote.",
    # Anglais : « buy » / « sell » ont des emplois factuels qu'il ne faut pas
    # confondre avec l'impératif (carnet d'ordres, catégorie d'analystes).
    "Buy orders reached 12,000 shares on the session.",
    "Sell-side coverage remains limited on the BRVM.",
    "Buy volume exceeded sell volume.",
    # L'infinitif AILLEURS qu'en tête de phrase reste explicatif, donc licite.
    "Les frais pour acheter une action s'élèvent à 1,2 %.",
]

for texte in FACTUELS:
    violations = check(texte)
    assert not violations, (
        f"FAUX POSITIF : {texte!r} bloqué sur "
        f"{[v['terme'] for v in violations]}"
    )
    assert enforce(texte) == texte

print(f"[factuel] {len(FACTUELS)}/{len(FACTUELS)} textes correctement laissés passer")

# --- 3. Détails de l'infraction (utilisables pour journaliser) --------------
v = check("Le titre est sous-évalué : achetez avant le détachement.")
assert len(v) >= 2, f"attendu >= 2 infractions, obtenu {len(v)}"
assert v[0]["position"] < v[1]["position"], "les infractions doivent être triées par position"
for infraction in v:
    assert infraction["terme"] and infraction["raison"] and infraction["extrait"]

print(f"[détail] infractions tracées : {[i['terme'] for i in v]}")

# --- 4. Cas limites ---------------------------------------------------------
assert check("") == [], "texte vide : aucune infraction"
assert check(None) == [], "None : aucune infraction (pas de crash)"
assert enforce("Cours du jour : 15 400 FCFA.") == "Cours du jour : 15 400 FCFA."

print("[limites] texte vide / None gérés")

# --- 5. Les READMEs annoncent des termes précis : ils DOIVENT être bloqués ----
# Ce test garde la documentation honnête. Les READMEs publics (EN et FR)
# promettent que le linter bloque ces termes ; si quelqu'un modifie _MOTIFS et
# casse l'un d'eux, ce test échoue AVANT que la promesse ne devienne un mensonge.
TERMES_ANNONCES_README = {
    # README.md (anglais)
    "buy": "Buy SONATEL now.",
    "sell": "Sell ETIT before the dividend.",
    "we recommend": "We recommend the banking sector.",
    "price target": "Price target: XOF 20,000.",
    "undervalued": "The stock is undervalued.",
    # docs/README.fr.md (français)
    "acheter": "Acheter SONATEL maintenant.",
    "vendre": "Vendre ETIT avant le détachement.",
    "nous recommandons": "Nous recommandons le secteur bancaire.",
    "objectif de cours": "Objectif de cours : 20 000 FCFA.",
    "sous-évalué": "Le titre est sous-évalué.",
}

for terme, phrase in TERMES_ANNONCES_README.items():
    assert check(phrase), (
        f"Le README annonce que « {terme} » est bloqué, mais {phrase!r} passe. "
        "Corriger le linter OU corriger le README — pas de promesse non tenue."
    )

print(f"[README] {len(TERMES_ANNONCES_README)} termes annoncés (EN+FR) → tous bloqués")
print("OK — linter éditorial conforme")
