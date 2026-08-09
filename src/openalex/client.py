"""Cliente minimo para la API de works de OpenAlex."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

import requests

BASE_URL = "https://api.openalex.org"


class OpenAlexError(RuntimeError):
    pass


@dataclass
class Paper:
    openalex_id: str
    title: str
    journal: str
    journal_openalex_id: str
    publication_year: int
    publication_date: str | None
    doi: str | None
    authors: list[str]
    abstract: str | None
    cited_by_count: int
    is_oa: bool
    oa_pdf_url: str | None
    landing_page_url: str | None
    raw: dict = field(repr=False)


def _mailto(mailto: str | None) -> str:
    mailto = mailto or os.environ.get("OPENALEX_MAILTO")
    if not mailto:
        raise OpenAlexError(
            "Falta un email de contacto para OpenAlex. Pasa mailto=... o define "
            "la variable de entorno OPENALEX_MAILTO (recomendado por OpenAlex para "
            "entrar en la 'polite pool', con limites mas altos y respuestas mas rapidas)."
        )
    return mailto


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex no da el abstract como texto plano sino como un indice invertido
    (palabra -> posiciones). Hay que reconstruir la oracion a partir de eso."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def _extract_authors(authorships: list[dict]) -> list[str]:
    return [a["author"]["display_name"] for a in authorships if a.get("author")]


def _extract_oa_pdf_url(work: dict) -> str | None:
    """Busca la mejor URL de PDF de acceso abierto disponible en el work."""
    best_oa = (work.get("best_oa_location") or {})
    if best_oa.get("pdf_url"):
        return best_oa["pdf_url"]

    primary = work.get("primary_location") or {}
    if primary.get("is_oa") and primary.get("pdf_url"):
        return primary["pdf_url"]

    for loc in work.get("locations") or []:
        if loc.get("pdf_url"):
            return loc["pdf_url"]

    return None


def _work_to_paper(work: dict) -> Paper:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    oa = work.get("open_access") or {}

    return Paper(
        openalex_id=work["id"],
        title=work.get("title") or work.get("display_name") or "(sin titulo)",
        journal=source.get("display_name") or "(revista desconocida)",
        journal_openalex_id=source.get("id") or "",
        publication_year=work.get("publication_year"),
        publication_date=work.get("publication_date"),
        doi=work.get("doi"),
        authors=_extract_authors(work.get("authorships") or []),
        abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
        cited_by_count=work.get("cited_by_count", 0),
        is_oa=bool(oa.get("is_oa")),
        oa_pdf_url=_extract_oa_pdf_url(work),
        landing_page_url=primary_location.get("landing_page_url"),
        raw=work,
    )


def fetch_papers(
    source_ids: str,
    from_year: int,
    limit: int = 5,
    sort: str = "cited_by_count:desc",
    mailto: str | None = None,
    extra_filters: str | None = None,
) -> list[Paper]:
    """Trae papers de un conjunto de revistas (por OpenAlex source id), publicados
    desde `from_year` en adelante.

    source_ids: IDs de OpenAlex separados por '|' (OR), p.ej. "S203860005|S88935262".
        Ver src/openalex/journals.py -> source_id_filter().
    """
    today = date.today()
    filters = [
        f"primary_location.source.id:{source_ids}",
        f"from_publication_date:{from_year}-01-01",
        f"to_publication_date:{today.isoformat()}",
        "type:article",
    ]
    if extra_filters:
        filters.append(extra_filters)

    params = {
        "filter": ",".join(filters),
        "sort": sort,
        "per_page": str(limit),
        "mailto": _mailto(mailto),
        "select": ",".join(
            [
                "id",
                "title",
                "display_name",
                "publication_year",
                "publication_date",
                "doi",
                "authorships",
                "abstract_inverted_index",
                "cited_by_count",
                "open_access",
                "best_oa_location",
                "primary_location",
                "locations",
            ]
        ),
    }

    resp = requests.get(f"{BASE_URL}/works", params=params, timeout=30)
    if resp.status_code != 200:
        raise OpenAlexError(f"OpenAlex respondio {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    return [_work_to_paper(w) for w in data.get("results", [])]
