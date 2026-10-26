import os
import re
import io
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlparse

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_DIR = os.path.dirname(os.path.abspath(__file__))
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")
NEBIUS_MODEL = os.getenv("NEBIUS_MODEL", "")

app = FastAPI(title="BioSage API", version="0.1.0")
app.mount("/static", StaticFiles(directory=APP_DIR), name="static")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BioSage/0.1 (educational research assistant)"})


class InvestigateRequest(BaseModel):
    question: str = Field(min_length=4, max_length=2000)
    level: str = "student"


class PaperRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2000)
    question: str = Field(default="Summarize this paper's research question, methods, main findings, and limitations.", max_length=2000)
    level: str = "student"


def _get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = SESSION.get(url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Scientific literature service could not be reached: {exc}") from exc


def search_papers(query: str, limit: int = 6) -> list[dict[str, Any]]:
    # Europe PMC supports open access metadata and abstracts for biomedical literature.
    data = _get_json(f"{EUROPE_PMC}/search", {
        "query": query,
        "format": "json",
        "pageSize": limit,
        "sort": "RELEVANCE",
        "resultType": "core",
    })
    papers = []
    for item in data.get("resultList", {}).get("result", []):
        pmcid = item.get("pmcid")
        doi = item.get("doi")
        pmid = item.get("pmid")
        if pmcid:
            link = f"https://europepmc.org/articles/{pmcid}"
        elif doi:
            link = f"https://doi.org/{doi}"
        elif pmid:
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        else:
            link = "https://europepmc.org/search?query=" + quote(item.get("title", query))
        papers.append({
            "title": item.get("title") or "Untitled paper",
            "authors": item.get("authorString", ""),
            "year": item.get("firstPublicationDate", "")[:4],
            "journal": item.get("journalTitle", ""),
            "abstract": item.get("abstractText", ""),
            "url": link,
            "doi": doi or "",
            "pmid": pmid or "",
            "pmcid": pmcid or "",
        })
    return papers


def _model_answer(instruction: str, papers: list[dict[str, Any]], level: str) -> str:
    if not NEBIUS_API_KEY or not NEBIUS_MODEL:
        return (
            "Literature results are shown below, but AI synthesis is not configured yet. "
            "Set NEBIUS_API_KEY and NEBIUS_MODEL in your environment to enable evidence-grounded explanations.\n\n"
            "Use the original paper links to inspect the abstract and full text. Search results alone are not enough "
            "to establish a scientific conclusion."
        )
    from openai import OpenAI

    client = OpenAI(
        api_key=NEBIUS_API_KEY,
        base_url=NEBIUS_BASE_URL,
    )
    compact = []
    for i, p in enumerate(papers, 1):
        compact.append(
            f"[Source {i}] {p['title']} ({p['year']}; {p['journal']})\n"
            f"Authors: {p['authors']}\nURL: {p['url']}\nAbstract: {p['abstract'] or '[No abstract available]'}"
        )
    system = (
        "You are BioSage, a careful scientific literature explainer. Use only the supplied source records for "
        "claims about specific studies. Do not invent papers, data, sample sizes, quotes, tables, or results. "
        "Clearly distinguish what a study reports from interpretation and from what remains unknown. "
        "If evidence is insufficient, say so. Never present preclinical findings as proven human outcomes. "
        "Do not provide personal medical advice. Cite claims inline as [Source 1], [Source 2] matching the records. "
        "Explain limitations and disagreements where the supplied evidence supports doing so. "
        f"Write at this level: {level}."
    )
    user = (
        f"User request: {instruction}\n\nRetrieved literature records (metadata and abstracts may be incomplete):\n"
        + ("\n\n".join(compact) if compact else "[No relevant records were retrieved]")
        + "\n\nAnswer the user and be transparent about evidence gaps. Do not claim to have read full text, figures, or tables unless their contents were supplied."
    )
    try:
        result = client.chat.completions.create(
            model=NEBIUS_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1200,
        )
        return result.choices[0].message.content or "The model returned an empty response."
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Nebius model request failed. Check your model name, API key, and endpoint. Details: {exc}") from exc


def _paper_from_url(raw_url: str) -> dict[str, Any]:
    raw_url = raw_url.strip()
    # Accept DOI text as well as URLs, but never fetch arbitrary local/private addresses.
    if re.match(r"^10\.\d{4,9}/", raw_url, re.I):
        raw_url = "https://doi.org/" + raw_url
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Enter a valid https:// paper URL, DOI, PubMed link, or Europe PMC link.")
    host = parsed.hostname.lower()
    allowed = ("doi.org", "dx.doi.org", "pubmed.ncbi.nlm.nih.gov", "europepmc.org", "www.ebi.ac.uk", "pmc.ncbi.nlm.nih.gov")
    if not any(host == domain or host.endswith("." + domain) for domain in allowed):
        raise HTTPException(status_code=400, detail="For this first version, use a DOI, PubMed, Europe PMC, or PubMed Central link.")
    doi_match = re.search(r"10\.\d{4,9}/[^\s?#]+", raw_url, re.I)
    if doi_match:
        doi = doi_match.group(0).rstrip(".,)")
        data = _get_json(f"{EUROPE_PMC}/search", {"query": f'DOI:"{doi}"', "format": "json", "resultType": "core", "pageSize": 1})
        items = data.get("resultList", {}).get("result", [])
        if items:
            return search_papers(f'DOI:"{doi}"', 1)[0]
    pmid_match = re.search(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|[?&]term=)(\d{5,})", raw_url)
    if pmid_match:
        return search_papers(f"EXT_ID:{pmid_match.group(1)} AND SRC:MED", 1)[0] if search_papers(f"EXT_ID:{pmid_match.group(1)} AND SRC:MED", 1) else {}
    pmcid_match = re.search(r"(PMC\d+)", raw_url, re.I)
    if pmcid_match:
        found = search_papers(f"EXT_ID:{pmcid_match.group(1)} AND SRC:PMC", 1)
        if found:
            return found[0]
    # For a supported publisher URL that has no resolvable identifier, don't pretend we read its content.
    raise HTTPException(status_code=422, detail="I couldn't resolve this link to a paper record. Try its DOI, PubMed/Europe PMC link, or upload the PDF once PDF support is enabled.")


@app.get("/")
def home():
    return FileResponse(os.path.join(APP_DIR, "index.html"))


@app.get("/api/health")
def health():
    return {"status": "ok", "model_configured": bool(NEBIUS_API_KEY and NEBIUS_MODEL)}


@app.post("/api/investigate")
def investigate(request: InvestigateRequest):
    papers = search_papers(request.question, 6)
    answer = _model_answer(request.question, papers, request.level)
    return {"answer": answer, "papers": papers, "model_used": bool(NEBIUS_API_KEY and NEBIUS_MODEL)}


@app.post("/api/paper")
def read_paper(request: PaperRequest):
    paper = _paper_from_url(request.url)
    if not paper:
        raise HTTPException(status_code=404, detail="No matching paper record was found.")
    # This first implementation uses the metadata/abstract available through Europe PMC.
    # Full-text, table, and figure extraction is a later implementation step.
    instruction = (
        f"User provided this paper: {paper.get('title')} ({paper.get('url')}). "
        f"User asks: {request.question}. Use the supplied abstract and metadata only; "
        "clearly disclose that full text, tables, and figures have not been parsed in this version."
    )
    answer = _model_answer(instruction, [paper], request.level)
    return {"answer": answer, "papers": [paper], "model_used": bool(NEBIUS_API_KEY and NEBIUS_MODEL)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
