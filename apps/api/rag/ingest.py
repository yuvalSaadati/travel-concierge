# apps/api/rag/ingest.py
from __future__ import annotations

import os, time, hashlib, requests
from pathlib import Path
from typing import List, Iterable, Optional

from tqdm import tqdm

# LangChain bits (works with LC 0.2+)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader, WebBaseLoader, WikipediaLoader

PERSIST_DIR = "vectorstore"
DATA_DIR = Path("data/guides")

# ---------- CONFIG: toggle sources ----------
ENABLE_LOCAL_FILES   = False   # data/guides/*.md (your existing guides)
ENABLE_WIKIVOYAGE   = True   # city travel guides (no key)
ENABLE_WIKIPEDIA    = True   # background pages via WikipediaLoader (no key)
ENABLE_OVERPASS_OSM = False   # POI names from OpenStreetMap (no key)
ENABLE_URLS         = False  # scrape arbitrary URLs (no key)

# Cities to fetch from external sources
CITIES = [
    "Rome", "Tokyo", "Paris", "London", "Barcelona", "Berlin",
    "Amsterdam", "Prague", "Vienna", "Istanbul", "Athens",
]

# Optional extra URLs to crawl (set ENABLE_URLS=True to use)
URLS: List[str] = [
    # "https://www.rome.net/sights",
    # "https://www.turismoroma.it/en",
]

# ---------- helpers ----------

def _doc_id(text: str, meta: dict) -> str:
    """Stable hash for deduping."""
    h = hashlib.sha256()
    h.update(text.strip().encode("utf-8"))
    if "source" in meta:
        h.update(str(meta["source"]).encode("utf-8"))
    if "title" in meta:
        h.update(str(meta["title"]).encode("utf-8"))
    return h.hexdigest()

def _dedupe(docs: Iterable[Document]) -> List[Document]:
    seen = set()
    out: List[Document] = []
    for d in docs:
        did = _doc_id(d.page_content, d.metadata or {})
        if did not in seen:
            seen.add(did)
            out.append(d)
    return out

def geocode(city: str) -> Optional[tuple[float, float, str]]:
    """Open-Meteo geocoder (no key). Returns (lat, lon, tz)."""
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=20,
    )
    r.raise_for_status()
    js = r.json()
    if not js.get("results"):
        return None
    res = js["results"][0]
    return float(res["latitude"]), float(res["longitude"]), res.get("timezone", "auto")
API = "https://en.wikivoyage.org/w/api.php"
HEADERS = {
    # Put something identifying + contact. This matters for Wikimedia.
    "User-Agent": "travel-concierge/0.1 (https://example.com; contact: you@example.com)"
}

def wikivoyage_docs(cities: List[str]) -> List[Document]:
    """Fetch plain-text extracts from Wikivoyage (CC BY-SA)."""
    docs: List[Document] = []
    API = "https://en.wikivoyage.org/w/api.php"
    for city in cities:
        try:
            params = {
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "format": "json",
                "titles": city,
                "redirects": 1,
                "formatversion": 2,
                    }
            
            r = requests.get(API, params=params, timeout=30, headers=HEADERS)
            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            text = pages[0]["extract"].strip()
            if text:
                docs.append(Document(
                    page_content=text,
                    metadata={"source": "wikivoyage", "title": city}
                ))
            time.sleep(0.3)  
        except Exception as e:
            print("Error:", type(e).__name__, "-", e)

    return docs

def wikipedia_docs(cities: List[str]) -> List[Document]:
    """Use LangChain WikipediaLoader to pull concise pages."""
    docs: List[Document] = []
    for city in cities:
        try:
            loader = WikipediaLoader(query=city, load_max_docs=1, lang="en")
            docs.extend(loader.load())
            time.sleep(0.2)
        except Exception as e:
            print("Error:", type(e).__name__, "-", e)
    # tag metadata so you can filter later
    for d in docs:
        d.metadata.setdefault("source", "wikipedia")
    return docs

def overpass_poi_docs(cities: List[str], radius_m: int = 3000, per_city_limit: int = 40) -> List[Document]:
    """Get POI names from OSM (tourism/historic) around city center. No key."""
    OVERPASS = "https://overpass-api.de/api/interpreter"
    docs: List[Document] = []
    for city in cities:
        try:
            geo = geocode(city)
            if not geo:
                continue
            lat, lon, _tz = geo
            q = f"""
            [out:json][timeout:25];
            (
              node(around:{radius_m},{lat},{lon})["tourism"];
              way(around:{radius_m},{lat},{lon})["tourism"];
              node(around:{radius_m},{lat},{lon})["historic"];
              way(around:{radius_m},{lat},{lon})["historic"];
            );
            out center {per_city_limit};
            """
            r = requests.post(OVERPASS, data={"data": q}, timeout=40)
            r.raise_for_status()
            elements = r.json().get("elements", [])
            names = []
            for el in elements:
                name = (el.get("tags") or {}).get("name")
                if name and name not in names:
                    names.append(name)
                if len(names) >= per_city_limit:
                    break
            # Turn each city’s POI list into a small markdown guide
            if names:
                text = f"# Points of Interest in {city}\n\n" + "\n".join(f"- {n}" for n in names)
                docs.append(Document(page_content=text, metadata={"source": "osm_overpass", "title": f"{city} POIs"}))
            time.sleep(0.8)  # be polite to Overpass
        except Exception:
            continue
    return docs

def local_md_docs(dirpath: Path) -> List[Document]:
    if not dirpath.exists():
        return []
    docs: List[Document] = []
    for p in dirpath.glob("*.md"):
        try:
            docs += TextLoader(str(p), encoding="utf-8").load()
        except Exception:
            continue
    for d in docs:
        d.metadata.setdefault("source", "local")
    return docs

def url_docs(urls: List[str]) -> List[Document]:
    if not urls:
        return []
    loader = WebBaseLoader(urls)
    docs = loader.load()
    for d in docs:
        d.metadata.setdefault("source", "web")
    return docs

# ---------- main ----------

def main():
    # 1) Gather documents from all enabled sources
    docs: List[Document] = []

    if ENABLE_LOCAL_FILES:
        docs.extend(local_md_docs(DATA_DIR))

    if ENABLE_WIKIVOYAGE:
        docs.extend(wikivoyage_docs(CITIES))

    if ENABLE_WIKIPEDIA:
        docs.extend(wikipedia_docs(CITIES))

    if ENABLE_OVERPASS_OSM:
        docs.extend(overpass_poi_docs(CITIES))

    if ENABLE_URLS:
        docs.extend(url_docs(URLS))

    if not docs:
        print("No documents found. Enable at least one source or add files to data/guides/*.md")
        return

    # 2) Deduplicate (cheap content hash)
    docs = _dedupe(docs)

    # 3) Split
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    chunks = splitter.split_documents(docs)

    # 4) Embed + index (Chroma with HF embeddings)
    emb = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2",
                                encode_kwargs={"normalize_embeddings": True})
    db = Chroma(collection_name="guides",
                persist_directory=PERSIST_DIR,
                embedding_function=emb)

    # add in batches
    BATCH = 200
    for i in tqdm(range(0, len(chunks), BATCH), desc="Indexing"):
        db.add_documents(chunks[i:i+BATCH])

    print(f"Indexed {len(chunks)} chunks from {len(docs)} source docs into {PERSIST_DIR}")

if __name__ == "__main__":
    main()
