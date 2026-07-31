"""Tests des fondamentaux : parsing pur + extraction PDF réelle (fixture)."""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from brvm_scraper import fundamentals as F

# --- 1. Fonctions pures (parsing) ---
assert F._to_number("31 000") == 31000.0
assert F._to_number("12,5") == 12.5
assert F._to_number("1 234,56") == 1234.56
assert F._to_number("-") is None
assert F._to_number("") is None
assert F._to_number(None) is None
print("[to_number] OK")

header = ["Symbole", "Cours", "PER", "Rendement (%)", "Capitalisation (FCFA)", "BPA"]
cols = F.detect_columns(header)
print(f"[detect_columns] {cols}")
assert cols == {"symbole": 0, "cours": 1, "per": 2, "rendement": 3,
                "capitalisation": 4, "bpa": 5}, cols

table = [header,
         ["SNTS", "31 000", "12,5", "8,10", "3 100 000 000 000", "2 480"],
         ["ONTBF", "2 790", "9,2", "6,45", "188 325 000 000", "303"],
         ["TOTAL", "", "", "", "5 552 500 000 000", ""]]
parsed = F.parse_fundamentals_table(table)
print(f"[parse_table] {len(parsed)} titres (ligne TOTAL bien ignorée)")
assert len(parsed) == 2, parsed
assert parsed[0] == {"symbole": "SNTS", "cours": 31000.0, "per": 12.5,
                     "rendement": 8.10, "capitalisation": 3.1e12, "bpa": 2480.0}, parsed[0]
print(f"  SNTS -> PER {parsed[0]['per']}, rendement {parsed[0]['rendement']}%")

# --- 2. Extraction PDF réelle (BOC du 21/07/2026, brvm.org) ---
pdf_bytes = (pathlib.Path(__file__).parent / "boc_fixture.pdf").read_bytes()
tables = F.extract_tables(pdf_bytes)
print("\n[extract_tables] " + str(len(tables)) + " tableau(x) trouve(s) dans le PDF")
assert len(tables) >= 1

all_fund = []
for t in tables:
    all_fund.extend(F.parse_fundamentals_table(t))
print("[pipeline PDF complet] " + str(len(all_fund)) + " titres extraits")
for f in all_fund:
    print("  " + f["symbole"])
# Le BOC réel contient les 47 valeurs cotées
assert len(all_fund) >= 40, "attendu >= 40 titres, obtenu " + str(len(all_fund))
syms = {f["symbole"] for f in all_fund}
# Les 5 tickers de référence doivent tous être présents
TICKERS_REF = {"SNTS", "ONTBF", "CBIBF", "BOABF", "ECOC"}
assert TICKERS_REF.issubset(syms), "Tickers manquants : " + str(TICKERS_REF - syms)

print("\n>>> TESTS FONDAMENTAUX OK <<<")
