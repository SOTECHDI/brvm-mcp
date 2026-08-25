"""
Relevé quotidien automatique, exécuté par le serveur lui-même.

Pourquoi ici et pas dans un cron externe : sur Railway, un volume ne peut être
attaché qu'à UN service. Si le relevé tournait dans un service séparé, il
écrirait dans une base que le serveur MCP ne lit pas. En le lançant depuis le
processus du serveur, la base historisée est bien celle que les clients
interrogent.

Le relevé ne démarre qu'en mode HTTP (déploiement). En mode stdio (usage local
via uvx), rien ne tourne : chaque utilisateur lance `snapshot.py` s'il le
souhaite.

Réglages par variables d'environnement :
  BRVM_AUTO_SNAPSHOT   "1" (défaut) pour activer, "0" pour désactiver
  BRVM_SNAPSHOT_HEURES heures UTC de tentative, ex. "12,14,16" (défaut)
  BRVM_DB              chemin de la base — sur Railway : /data/brvm_history.db
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime, timezone

# La BRVM ne cote qu'une fois par jour (fixing vers 10h45 GMT). On tente après,
# puis on retente : le site est régulièrement injoignable (erreurs SSL, délais).
HEURES_DEFAUT = "12,14,16"
PAUSE = 600           # 10 minutes entre deux vérifications
PAUSE_DEMARRAGE = 20  # laisse le serveur répondre au healthcheck avant de scraper


def _heures() -> list[int]:
    brut = os.getenv("BRVM_SNAPSHOT_HEURES", HEURES_DEFAUT)
    heures = []
    for morceau in brut.split(","):
        morceau = morceau.strip()
        if morceau.isdigit() and 0 <= int(morceau) <= 23:
            heures.append(int(morceau))
    return heures or [12, 14, 16]


def _derniere_seance_en_base():
    """Date de la dernière séance déjà historisée, ou None si base vide."""
    from .storage import db_stats
    try:
        valeur = db_stats().get("derniere_seance")
        return date.fromisoformat(valeur) if valeur else None
    except Exception:
        return None  # base absente ou vide : ce n'est pas une erreur


def _rattrapage(log):
    """
    Au démarrage, comble la séance manquante si le serveur a redémarré en
    dehors des créneaux (redéploiement, panne, mise à l'échelle).
    Renvoie la date enregistrée, ou None.
    """
    aujourdhui = datetime.now(timezone.utc).date()
    deja = _derniere_seance_en_base()

    if deja == aujourdhui:
        log.info("[releve] seance %s deja en base — pas de rattrapage", deja)
        return aujourdhui

    log.info("[releve] rattrapage au demarrage (derniere seance en base : %s)",
             deja or "aucune")
    try:
        from .storage import snapshot_daily
        resume = snapshot_daily()
        log.info("[releve] rattrapage OK — %s", resume)
        return aujourdhui
    except Exception as e:
        log.warning("[releve] rattrapage impossible (creneaux du jour prendront le relais) : %s", e)
        return None


def _boucle(log) -> None:
    from .storage import snapshot_daily

    heures = _heures()
    log.info("[releve] planificateur actif — tentatives a %s UTC, jours ouvres",
             ", ".join(f"{h}h" for h in heures))

    # Le serveur doit d'abord être joignable : le healthcheck Railway ne doit
    # pas échouer pendant qu'on scrape.
    time.sleep(PAUSE_DEMARRAGE)
    dernier_succes = _rattrapage(log)

    while True:
        try:
            maintenant = datetime.now(timezone.utc)
            aujourdhui = maintenant.date()

            jour_ouvre = maintenant.weekday() < 5          # lundi=0 … vendredi=4
            bonne_heure = maintenant.hour in heures
            a_faire = dernier_succes != aujourdhui

            if jour_ouvre and bonne_heure and a_faire:
                try:
                    resume = snapshot_daily()
                    dernier_succes = aujourdhui
                    log.info("[releve] OK — %s", resume)
                except Exception as e:
                    # brvm.org est souvent indisponible : on ne bloque pas le
                    # serveur, on retentera à l'heure suivante.
                    log.warning("[releve] echec (nouvelle tentative plus tard) : %s", e)

        except Exception as e:  # garde-fou : le thread ne doit jamais mourir
            log.warning("[releve] erreur inattendue du planificateur : %s", e)

        time.sleep(PAUSE)


def demarrer(log) -> bool:
    """
    Lance le relevé quotidien en tâche de fond. Renvoie True s'il a démarré.
    À n'appeler qu'en mode HTTP.
    """
    if os.getenv("BRVM_AUTO_SNAPSHOT", "1") != "1":
        log.info("[releve] desactive (BRVM_AUTO_SNAPSHOT=0)")
        return False

    base = os.getenv("BRVM_DB", "")
    if base:
        log.info("[releve] base historisee : %s", base)
    else:
        log.warning(
            "[releve] BRVM_DB non definie — la base sera ecrite dans le conteneur "
            "et PERDUE a chaque redeploiement. Montez un volume et definissez "
            "BRVM_DB=/data/brvm_history.db"
        )

    threading.Thread(target=_boucle, args=(log,), daemon=True, name="releve-brvm").start()
    return True
