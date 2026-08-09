"""
Resuelve los IDs de OpenAlex para la lista de revistas de economia por ISSN,
y los deja ordenados por `summary_stats.2yr_mean_citedness` (proxy de impacto/ranking).

Este script solo se necesita para *regenerar* `src/openalex/journals.py` si se
quiere ajustar la lista de revistas o refrescar el ranking de impacto. El
pipeline normal no lo llama: usa los IDs ya resueltos en journals.py para no
gastar cuota de la API en cada corrida.

Uso:
    OPENALEX_MAILTO=tu@email.com python scripts/resolve_journals.py
"""

import json
import os
import sys
import urllib.parse
import urllib.request

# ISSN de referencia (top-5 + revistas de campo bien consideradas en economia).
# Ajustar esta lista y volver a correr el script para refrescar journals.py.
JOURNAL_ISSNS = {
    "American Economic Review": "0002-8282",
    "Quarterly Journal of Economics": "0033-5533",
    "Journal of Political Economy": "0022-3808",
    "Econometrica": "0012-9682",
    "Review of Economic Studies": "0034-6527",
    "Journal of Economic Literature": "0022-0515",
    "Journal of Economic Perspectives": "0895-3309",
    "American Economic Journal: Applied Economics": "1945-7782",
    "American Economic Journal: Economic Policy": "1945-7731",
    "American Economic Journal: Macroeconomics": "1945-7707",
    "American Economic Journal: Microeconomics": "1945-7669",
    "Review of Economics and Statistics": "0034-6535",
    "Journal of Public Economics": "0047-2727",
    "Journal of Labor Economics": "0734-306X",
    "Journal of Development Economics": "0304-3878",
    "Journal of Health Economics": "0167-6296",
    "Journal of Human Resources": "0022-166X",
    "Journal of Econometrics": "0304-4076",
    "Journal of the European Economic Association": "1542-4766",
    "Economic Journal": "0013-0133",
    "International Economic Review": "0020-6598",
    "Journal of Monetary Economics": "0304-3932",
    "Journal of International Economics": "0022-1996",
    "RAND Journal of Economics": "0741-6261",
    "Games and Economic Behavior": "0899-8256",
    "Journal of Finance": "0022-1082",
    "Journal of Financial Economics": "0304-405X",
    "Review of Financial Studies": "0893-9454",
    "World Bank Economic Review": "0258-6770",
    "Experimental Economics": "1386-4157",
    "Journal of Urban Economics": "0094-1190",
    "Regional Science and Urban Economics": "0166-0462",
    "Journal of Population Economics": "0933-1433",
    "Demography": "0070-3370",
    "Journal of Applied Econometrics": "0883-7252",
    "Journal of Business & Economic Statistics": "0735-0015",
    "Quantitative Economics": "1759-7323",
    "Theoretical Economics": "1933-6837",
    "European Economic Review": "0014-2921",
    "Labour Economics": "0927-5371",
    "Economics of Education Review": "0272-7757",
}

TOP_N = 40


def main() -> None:
    mailto = os.environ.get("OPENALEX_MAILTO")
    if not mailto:
        sys.exit("Falta OPENALEX_MAILTO en el entorno (requerido por la polite pool de OpenAlex).")

    issns = "|".join(JOURNAL_ISSNS.values())
    params = {
        "filter": f"issn:{issns}",
        "per_page": "100",
        "select": "id,display_name,issn,issn_l,works_count,summary_stats",
        "mailto": mailto,
    }
    url = "https://api.openalex.org/sources?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)

    results = data["results"]
    found_issns = {issn for r in results for issn in (r.get("issn") or [])}
    missing = [name for name, issn in JOURNAL_ISSNS.items() if issn not in found_issns]
    if missing:
        print("ADVERTENCIA: no se resolvieron estas revistas:", file=sys.stderr)
        for name in missing:
            print(f"  - {name} ({JOURNAL_ISSNS[name]})", file=sys.stderr)

    ranked = sorted(
        results,
        key=lambda r: (r.get("summary_stats") or {}).get("2yr_mean_citedness") or 0,
        reverse=True,
    )[:TOP_N]

    n = len(ranked)
    print(f'"""Top {n} revistas de economia, ordenadas por 2yr_mean_citedness."""')
    print()
    for i, r in enumerate(ranked, start=1):
        oaid = r["id"].rsplit("/", 1)[-1]
        weight = n - i + 1
        print(
            f'Journal(name={r["display_name"]!r}, openalex_id={oaid!r}, '
            f'issn_l={r.get("issn_l")!r}, rank={i}, weight={weight}, '
            f'two_yr_mean_citedness={(r.get("summary_stats") or {}).get("2yr_mean_citedness")!r}),'
        )


if __name__ == "__main__":
    main()
