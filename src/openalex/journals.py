"""
Top 40 revistas de economia (ranking de referencia para el pipeline de papers).

Los IDs de OpenAlex se resolvieron una sola vez por ISSN (ver scripts/resolve_journals.py
en el historial de este cambio) y se dejan hardcodeados aqui para no gastar cuota de la
API de OpenAlex resolviendo las mismas revistas en cada corrida del pipeline.

`rank` es la posicion en este ranking (1 = mayor impacto). `weight` es un peso lineal
derivado del rank (40 para el puesto 1, 1 para el puesto 40) pensado para usarse como
prior en el paso de seleccion/priorizacion de la Parte B, para que un paper en una
revista mejor rankeada pese mas que uno en una revista mas abajo en la lista.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Journal:
    name: str
    openalex_id: str
    issn_l: str | None
    rank: int
    weight: int
    two_yr_mean_citedness: float | None


TOP_40_ECON_JOURNALS: list[Journal] = [
    Journal(name="The Quarterly Journal of Economics", openalex_id="S203860005", issn_l='0033-5533', rank=1, weight=40, two_yr_mean_citedness=19.385714285714286),
    Journal(name="The Review of Economic Studies", openalex_id="S88935262", issn_l='0034-6527', rank=2, weight=39, two_yr_mean_citedness=15.7),
    Journal(name="American Economic Review", openalex_id="S23254222", issn_l='0002-8282', rank=3, weight=38, two_yr_mean_citedness=14.574074074074074),
    Journal(name="The Journal of Finance", openalex_id="S5353659", issn_l='0022-1082', rank=4, weight=37, two_yr_mean_citedness=12.365591397849462),
    Journal(name="Journal of Economic Literature", openalex_id="S127708089", issn_l='0022-0515', rank=5, weight=36, two_yr_mean_citedness=11.242105263157894),
    Journal(name="Review of Financial Studies", openalex_id="S170137484", issn_l='0893-9454', rank=6, weight=35, two_yr_mean_citedness=10.89922480620155),
    Journal(name="Journal of Financial Economics", openalex_id="S149240962", issn_l='0304-405X', rank=7, weight=34, two_yr_mean_citedness=10.865329512893982),
    Journal(name="The Journal of Economic Perspectives", openalex_id="S72880728", issn_l='0895-3309', rank=8, weight=33, two_yr_mean_citedness=7.731884057971015),
    Journal(name="Econometrica", openalex_id="S95464858", issn_l='0012-9682', rank=9, weight=32, two_yr_mean_citedness=7.124481327800829),
    Journal(name="American Economic Journal Applied Economics", openalex_id="S42893225", issn_l='1945-7782', rank=10, weight=31, two_yr_mean_citedness=7.023809523809524),
    Journal(name="Journal of Political Economy", openalex_id="S95323914", issn_l='0022-3808', rank=11, weight=30, two_yr_mean_citedness=6.151315789473684),
    Journal(name="Journal of International Economics", openalex_id="S198098467", issn_l='0022-1996', rank=12, weight=29, two_yr_mean_citedness=6.0120481927710845),
    Journal(name="American Economic Journal Economic Policy", openalex_id="S158011328", issn_l='1945-7731', rank=13, weight=28, two_yr_mean_citedness=5.846153846153846),
    Journal(name="Journal of Urban Economics", openalex_id="S147692640", issn_l='0094-1190', rank=14, weight=27, two_yr_mean_citedness=5.5479452054794525),
    Journal(name="American Economic Journal Macroeconomics", openalex_id="S170166683", issn_l='1945-7707', rank=15, weight=26, two_yr_mean_citedness=5.2682926829268295),
    Journal(name="Journal of Monetary Economics", openalex_id="S6711363", issn_l='0304-3932', rank=16, weight=25, two_yr_mean_citedness=4.814814814814815),
    Journal(name="The Review of Economics and Statistics", openalex_id="S180061323", issn_l='0034-6535', rank=17, weight=24, two_yr_mean_citedness=4.177570093457944),
    Journal(name="Journal of the European Economic Association", openalex_id="S165087003", issn_l='1542-4766', rank=18, weight=23, two_yr_mean_citedness=4.050314465408805),
    Journal(name="The Economic Journal", openalex_id="S45992627", issn_l='0013-0133', rank=19, weight=22, two_yr_mean_citedness=4.0256410256410255),
    Journal(name="Journal of Development Economics", openalex_id="S101209419", issn_l='0304-3878', rank=20, weight=21, two_yr_mean_citedness=3.7471264367816093),
    Journal(name="The RAND Journal of Economics", openalex_id="S34139249", issn_l='0741-6261', rank=21, weight=20, two_yr_mean_citedness=3.707317073170732),
    Journal(name="Journal of Public Economics", openalex_id="S199447588", issn_l='0047-2727', rank=22, weight=19, two_yr_mean_citedness=3.700636942675159),
    Journal(name="American Economic Journal Microeconomics", openalex_id="S96919139", issn_l='1945-7669', rank=23, weight=18, two_yr_mean_citedness=3.3795620437956204),
    Journal(name="Quantitative Economics", openalex_id="S156003414", issn_l='1759-7323', rank=24, weight=17, two_yr_mean_citedness=3.317757009345794),
    Journal(name="Journal of Applied Econometrics", openalex_id="S85739584", issn_l='0883-7252', rank=25, weight=16, two_yr_mean_citedness=3.2818181818181817),
    Journal(name="Journal of Population Economics", openalex_id="S18284184", issn_l='0933-1433', rank=26, weight=15, two_yr_mean_citedness=3.1869158878504673),
    Journal(name="Journal of Health Economics", openalex_id="S166621295", issn_l='0167-6296', rank=27, weight=14, two_yr_mean_citedness=3.0308370044052864),
    Journal(name="European Economic Review", openalex_id="S69338747", issn_l='0014-2921', rank=28, weight=13, two_yr_mean_citedness=2.990990990990991),
    Journal(name="Journal of Econometrics", openalex_id="S127742747", issn_l='0304-4076', rank=29, weight=12, two_yr_mean_citedness=2.892070484581498),
    Journal(name="Journal of Labor Economics", openalex_id="S8557221", issn_l='0734-306X', rank=30, weight=11, two_yr_mean_citedness=2.8551724137931034),
    Journal(name="The World Bank Economic Review", openalex_id="S2735890421", issn_l='0258-6770', rank=31, weight=10, two_yr_mean_citedness=2.677165354330709),
    Journal(name="Demography", openalex_id="S30543418", issn_l='0070-3370', rank=32, weight=9, two_yr_mean_citedness=2.4816326530612245),
    Journal(name="Theoretical Economics", openalex_id="S10997704", issn_l='1555-7561', rank=33, weight=8, two_yr_mean_citedness=2.4696969696969697),
    Journal(name="Regional Science and Urban Economics", openalex_id="S107631327", issn_l='0166-0462', rank=34, weight=7, two_yr_mean_citedness=2.388571428571429),
    Journal(name="International Economic Review", openalex_id="S179979277", issn_l='0020-6598', rank=35, weight=6, two_yr_mean_citedness=2.3091787439613527),
    Journal(name="Labour Economics", openalex_id="S163774179", issn_l='0927-5371', rank=36, weight=5, two_yr_mean_citedness=2.155425219941349),
    Journal(name="Economics of Education Review", openalex_id="S4888523", issn_l='0272-7757', rank=37, weight=4, two_yr_mean_citedness=1.8957345971563981),
    Journal(name="Journal of Business and Economic Statistics", openalex_id="S18095783", issn_l='0735-0015', rank=38, weight=3, two_yr_mean_citedness=1.7230769230769232),
    Journal(name="Experimental Economics", openalex_id="S181493553", issn_l='1386-4157', rank=39, weight=2, two_yr_mean_citedness=1.696969696969697),
    Journal(name="The Journal of Human Resources", openalex_id="S62957338", issn_l='0022-166X', rank=40, weight=1, two_yr_mean_citedness=1.356164383561644),
]


def source_id_filter() -> str:
    """Valor listo para el filtro primary_location.source.id de la API de works."""
    return "|".join(j.openalex_id for j in TOP_40_ECON_JOURNALS)


def weight_by_source_id() -> dict[str, int]:
    return {j.openalex_id: j.weight for j in TOP_40_ECON_JOURNALS}

