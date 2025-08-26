from typing import List, Dict, Any
from langchain_community.vectorstores import Chroma
from sentence_transformers import SentenceTransformer

PERSIST_DIR = "vectorstore"

class Retriever:
    def __init__(self):
        self.db = Chroma(collection_name="guides", persist_directory=PERSIST_DIR)
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

    def search(self, city: str, interests: List[str], k: int = 8) -> List[Dict[str, Any]]:
        query = f"{city} travel guide tips " + " ".join(interests or [])
        vec = self.embedder.encode(query)
        # Chroma API: similarity_search_by_vector
        docs = self.db.similarity_search_by_vector(vec, k=k)
        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]

retriever = Retriever()
