"""
Parte C: consecucion del PDF completo de un paper.

Orden de intentos (mas barato/confiable primero):
1. La URL de acceso abierto que ya trae OpenAlex (Parte A: Paper.oa_pdf_url).
2. Unpaywall, consultando por DOI.
3. Ubicaciones alternativas que ya trae OpenAlex (Paper.raw["locations"]) que
   apunten a un repositorio de working papers conocido (NBER, IZA, SSRN, RePEc,
   econstor, la pagina del autor via una universidad, etc.).
4. Si nada de lo anterior dio un PDF descargable, se le pide a la API de Claude
   (con la herramienta de busqueda web) que encuentre la version de working
   paper y se intenta descargar esa URL.

Nota de limitacion conocida: algunas editoriales (ej. Oxford University Press,
SSRN) bloquean descargas automatizadas desde IPs de datacenter con un 403,
aunque la URL sea publica y funcione en un navegador normal. Cuando eso pasa,
resolve_pdf igual devuelve la URL encontrada (para que quede el link como
referencia / intento manual) pero local_path queda en None.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import anthropic
import requests

from openalex.client import Paper

DEFAULT_MODEL = "claude-opus-5"

# Hosts de working papers / repositorios conocidos, para reconocer ubicaciones
# alternativas que OpenAlex ya trae en Paper.raw["locations"].
KNOWN_REPOSITORY_HOSTS = {
    "nber.org": "NBER",
    "iza.org": "IZA",
    "ssrn.com": "SSRN",
    "repec.org": "RePEc/IDEAS",
    "econstor.eu": "EconStor",
    "econpapers.repec.org": "RePEc/IDEAS",
}

_USER_AGENT = "papers-whatsapp-bot/0.1 (+mailto:{mailto})"

_WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "url": {"type": ["string", "null"]},
        "source": {
            "type": "string",
            "enum": ["NBER", "IZA", "SSRN", "RePEc/IDEAS", "EconStor", "author_page", "other", "none"],
        },
        "notes": {"type": "string"},
    },
    "required": ["found", "url", "source", "notes"],
    "additionalProperties": False,
}

_WEB_SEARCH_SYSTEM_PROMPT = """\
Buscas la version de working paper de un articulo academico de economia que no \
tiene una version de acceso abierto identificada todavia. Preferencia de fuentes, \
en este orden: NBER, IZA, SSRN, RePEc/IDEAS, EconStor, o la pagina personal/institucional \
de alguno de los autores. Si encuentras una URL que apunta directo a un archivo PDF, \
esa es la mejor respuesta. Si solo encuentras la landing page del working paper (sin \
URL directa al PDF), esa tambien sirve. No inventes una URL: si no encuentras nada \
confiable, found debe ser false y url null.\
"""


class PdfError(RuntimeError):
    pass


@dataclass
class PdfResolution:
    local_path: str | None
    url: str | None
    source: str | None
    version: str | None  # "published" | "working_paper" | None
    notes: str


def _slugify(paper: Paper) -> str:
    text = f"{paper.publication_year}-{paper.title}"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:80] or "paper"


def _looks_like_pdf_url(url: str) -> bool:
    return bool(url) and (url.lower().endswith(".pdf") or "pdf" in urlparse(url).path.lower())


def _unpaywall_pdf_url(doi: str | None, email: str) -> str | None:
    if not doi:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{clean_doi}",
            params={"email": email},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()

    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return best["url_for_pdf"]

    for loc in data.get("oa_locations") or []:
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"]

    return None


def _repository_location(paper: Paper) -> tuple[str, str] | None:
    for loc in paper.raw.get("locations") or []:
        pdf_url = loc.get("pdf_url")
        landing = loc.get("landing_page_url") or ""
        candidate = pdf_url or landing
        if not candidate:
            continue
        host = urlparse(candidate).netloc.lower()
        for known_host, label in KNOWN_REPOSITORY_HOSTS.items():
            if known_host in host:
                return candidate, label
    return None


def _download_pdf(url: str, out_path: Path, mailto: str, timeout: int = 30) -> bool:
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT.format(mailto=mailto)},
            allow_redirects=True,
        )
    except requests.RequestException:
        return False

    if resp.status_code != 200:
        return False

    content_type = resp.headers.get("Content-Type", "").lower()
    is_pdf = "pdf" in content_type or resp.content[:5] == b"%PDF-"
    if not is_pdf:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return True


_NBER_LANDING_RE = re.compile(r"nber\.org/papers/w(\d+)", re.IGNORECASE)


def _nber_direct_pdf_url(url: str) -> str | None:
    """NBER sirve landing pages en /papers/wNNNNN y los PDF en una ruta
    predecible; si la busqueda web solo trajo la landing page, probamos la
    ruta directa antes de rendirnos."""
    match = _NBER_LANDING_RE.search(url)
    if not match:
        return None
    paper_id = match.group(1)
    return f"https://www.nber.org/system/files/working_papers/w{paper_id}/w{paper_id}.pdf"


def _web_search_fallback(paper: Paper, api_key: str | None, model: str) -> tuple[str, str] | None:
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    user_prompt = (
        f"Titulo: {paper.title}\n"
        f"Autores: {', '.join(paper.authors) or '(desconocidos)'}\n"
        f"Anio: {paper.publication_year}\n"
        f"Revista (version publicada): {paper.journal}\n"
        f"DOI: {paper.doi or '(sin DOI)'}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_WEB_SEARCH_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": _WEB_SEARCH_SCHEMA},
        },
        messages=[{"role": "user", "content": user_prompt}],
    )

    if response.stop_reason == "refusal":
        return None

    for block in response.content:
        if block.type != "text":
            continue
        try:
            data = json.loads(block.text)
        except (json.JSONDecodeError, AttributeError):
            continue
        if data.get("found") and data.get("url"):
            return data["url"], data.get("source") or "web_search"

    return None


def resolve_pdf(
    paper: Paper,
    out_dir: str,
    unpaywall_email: str,
    anthropic_api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    use_web_search_fallback: bool = True,
) -> PdfResolution:
    """Intenta conseguir el PDF completo de un paper, en el orden descrito arriba."""
    out_path = Path(out_dir) / f"{_slugify(paper)}.pdf"

    candidates: list[tuple[str, str, str]] = []  # (url, source, version)

    if paper.oa_pdf_url:
        candidates.append((paper.oa_pdf_url, "openalex", "published" if paper.is_oa else "unknown"))

    up_url = _unpaywall_pdf_url(paper.doi, unpaywall_email)
    if up_url and up_url not in {c[0] for c in candidates}:
        candidates.append((up_url, "unpaywall", "published"))

    repo = _repository_location(paper)
    if repo:
        repo_url, repo_label = repo
        if repo_url not in {c[0] for c in candidates}:
            candidates.append((repo_url, f"openalex_location:{repo_label}", "working_paper"))

    for url, source, version in candidates:
        if _download_pdf(url, out_path, unpaywall_email):
            return PdfResolution(str(out_path), url, source, version, "")

    if not use_web_search_fallback:
        return PdfResolution(None, None, None, None, "No se encontro PDF y el fallback de busqueda web esta desactivado.")

    found = _web_search_fallback(paper, anthropic_api_key, model)
    if not found:
        return PdfResolution(None, None, None, None, "No se encontro ninguna version descargable (ni OA ni working paper via busqueda web).")

    ws_url, ws_source = found
    if _download_pdf(ws_url, out_path, unpaywall_email):
        return PdfResolution(str(out_path), ws_url, f"web_search:{ws_source}", "working_paper", "")

    direct_url = _nber_direct_pdf_url(ws_url)
    if direct_url and _download_pdf(direct_url, out_path, unpaywall_email):
        return PdfResolution(str(out_path), direct_url, f"web_search:{ws_source}", "working_paper", "")

    return PdfResolution(
        None,
        ws_url,
        f"web_search:{ws_source}",
        "working_paper",
        "Se encontro una URL pero no se pudo descargar un PDF valido "
        "(posible bloqueo anti-bot del sitio, o la URL es una landing page sin PDF directo).",
    )
