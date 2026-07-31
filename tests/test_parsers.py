"""Tests de parsing sur fixture (pas de réseau requis)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from unittest.mock import patch
FIXTURE = (pathlib.Path(__file__).parent / "fixture_home.html").read_text()

with patch("brvm_scraper.client.get_html", return_value=FIXTURE), \
     patch("brvm_scraper.quotes.get_html", return_value=FIXTURE), \
     patch("brvm_scraper.dividends.get_html", return_value=FIXTURE):

    from brvm_scraper import quotes, dividends

    q = quotes.get_quotes()
    print(f"[quotes] {len(q)} titres parsés")
    assert len(q) == 47, f"Attendu 47, obtenu {len(q)}"
    snts = quotes.get_quotes("SNTS")[0]
    assert snts == {"symbole": "SNTS", "cours_fcfa": 31000, "variation_pct": -0.32}, snts
    print(f"  SNTS -> {snts}")

    idx = quotes.get_indices()
    print(f"[indices] {idx}")
    assert len(idx) == 3

    act = quotes.get_market_activity()
    print(f"[activité] transactions = {act['valeur_transactions_fcfa']:,} FCFA")
    assert act["valeur_transactions_fcfa"] == 1846902067

    s = quotes.get_market_summary()
    print(f"[résumé] top1={s['top_5'][0]['symbole']} ({s['top_5'][0]['variation_pct']}%) "
          f"flop1={s['flop_5'][0]['symbole']} ({s['flop_5'][0]['variation_pct']}%)")
    assert s["top_5"][0]["symbole"] == "CBIBF"
    assert s["flop_5"][0]["symbole"] == "UNLC"

    ann = dividends.get_dividend_announcements()
    print(f"\n[dividendes] {len(ann)} annonces (coupons obligataires exclus)")
    for a in ann:
        print(f"  {a['emetteur']:22} {a['ticker'] or '???':6} {a['date_paiement']}  "
              f"{a['dividende_fcfa_par_action']:>8} FCFA")
    assert len(ann) == 5, f"Attendu 5 dividendes, obtenu {len(ann)}"

    ry = dividends.compute_dividend_yield()
    print(f"\n[rendements] classés par rendement décroissant :")
    for r in ry:
        print(f"  {r['ticker']:6} {r['rendement_pct']:>6.2f}%  "
              f"(div {r['dividende_fcfa_par_action']} / cours {r['cours_actuel_fcfa']:,})")

print("\n>>> TOUS LES TESTS PASSENT <<<")
