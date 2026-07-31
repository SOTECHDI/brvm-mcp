"""Test de l'historisation : simule 3 séances et vérifie tendances + idempotence."""
import sys, pathlib, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from brvm_scraper import storage

# 3 jours simulés de cours pour SNTS (31000 -> 31500 -> 32000) et ONTBF stable
SEANCES = {
    "2026-07-13": [{"symbole": "SNTS", "cours_fcfa": 31000, "variation_pct": 0.0},
                   {"symbole": "ONTBF", "cours_fcfa": 2790, "variation_pct": 0.0}],
    "2026-07-14": [{"symbole": "SNTS", "cours_fcfa": 31500, "variation_pct": 1.61},
                   {"symbole": "ONTBF", "cours_fcfa": 2790, "variation_pct": 0.0}],
    "2026-07-15": [{"symbole": "SNTS", "cours_fcfa": 32000, "variation_pct": 1.59},
                   {"symbole": "ONTBF", "cours_fcfa": 2800, "variation_pct": 0.36}],
}
INDICES = [{"indice": "BRVM-C", "valeur": 474.92, "variation_pct": 0.95}]
DIVS = [{"emetteur": "SIB", "ticker": "SIBC", "date_paiement": "2026-07-31",
         "dividende_fcfa_par_action": 425.0}]

tmp = tempfile.mktemp(suffix=".db")

for jour, quotes in SEANCES.items():
    with patch.object(storage, "get_quotes", return_value=quotes), \
         patch.object(storage, "get_indices", return_value=INDICES), \
         patch.object(storage, "get_dividend_announcements", return_value=DIVS), \
         patch.object(storage, "_seance_date", return_value=jour):
        r = storage.snapshot_daily(tmp)
        print(f"snapshot {jour}: {r['titres_enregistres']} titres")

# --- Idempotence : rejouer le dernier jour ne doit rien dupliquer ---
with patch.object(storage, "get_quotes", return_value=SEANCES["2026-07-15"]), \
     patch.object(storage, "get_indices", return_value=INDICES), \
     patch.object(storage, "get_dividend_announcements", return_value=DIVS), \
     patch.object(storage, "_seance_date", return_value="2026-07-15"):
    storage.snapshot_daily(tmp)  # rejoué

stats = storage.db_stats(tmp)
print(f"\n[stats] {stats}")
assert stats["nb_seances_couvertes"] == 3, f"idempotence cassée: {stats}"
assert stats["lignes_cours"] == 6, f"attendu 6 lignes (3j x 2 titres), obtenu {stats['lignes_cours']}"
assert stats["annonces_dividendes"] == 1, "dividende dupliqué"

hist = storage.get_price_history("SNTS", db_path=tmp)
print(f"\n[historique SNTS] {len(hist)} points:")
for h in hist:
    print(f"  {h['date_seance']}  {h['cours_fcfa']:,} FCFA  ({h['variation_pct']:+}%)")

perf = storage.get_performance("SNTS", db_path=tmp)
print(f"\n[performance SNTS] {perf['cours_debut']:,} -> {perf['cours_fin']:,} = "
      f"{perf['variation_pct']:+}% sur {perf['nb_seances']} séances")
assert perf["variation_pct"] == 3.23, perf

perf_ontbf = storage.get_performance("ONTBF", db_path=tmp)
print(f"[performance ONTBF] {perf_ontbf['variation_pct']:+}%")
assert perf_ontbf["variation_pct"] == 0.36

os.remove(tmp)
print("\n>>> TESTS HISTORISATION OK <<<")
