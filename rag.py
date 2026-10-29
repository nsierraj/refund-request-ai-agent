"""Step 6: retrieval (the "R" in RAG), written by hand so you can see it.

    python rag.py build                          # read policies/, embed, save the index
    python rag.py "can I return a gift?"         # search only, no LLM involved

How it works:
  1. Split each file in policies/ into chunks, one per "## " section.
  2. Turn each chunk into an embedding: a list of 768 numbers that captures
     what the text is about. Similar meaning -> similar numbers.
  3. To search, embed the question the same way and rank chunks by cosine
     similarity (how closely two lists of numbers point the same direction).

No vector database: the index is a JSON file and the math is ten lines of
Python. Chroma, pgvector, OpenSearch and Bedrock Knowledge Bases do the
same thing, faster and at scale.
"""

import json
import math
import os
import sys
from pathlib import Path

import ollama

HERE = Path(__file__).parent
POLICY_DIR = HERE / "policies"
INDEX_PATH = HERE / "policy_index.json"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
TOP_K = 3

# nomic-embed-text was trained with these prefixes. They tell it whether a
# text is something to be found or something doing the finding.
DOC_PREFIX, QUERY_PREFIX = "search_document: ", "search_query: "


def chunk_policies():
    """One chunk per '## ' section, labeled with its file and heading."""
    chunks = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        title, section, lines = path.stem, None, []
        for line in path.read_text().splitlines() + ["## "]:  # sentinel flushes the last section
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                if section and any(l.strip() for l in lines):
                    text = " ".join(l.strip() for l in lines if l.strip())
                    chunks.append({"source": path.name, "section": section,
                                   "text": f"{title} - {section}: {text}"})
                section, lines = line[3:].strip(), []
            else:
                lines.append(line)
    return chunks


def embed(texts, prefix):
    return ollama.embed(model=EMBED_MODEL, input=[prefix + t for t in texts]).embeddings


def build_index():
    chunks = chunk_policies()
    vectors = embed([c["text"] for c in chunks], DOC_PREFIX)
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = list(vector)
    INDEX_PATH.write_text(json.dumps({"model": EMBED_MODEL, "chunks": chunks}))
    print(f"Indexed {len(chunks)} chunks from {POLICY_DIR.name}/ "
          f"({len(chunks[0]['embedding'])} numbers each) -> {INDEX_PATH.name}")


def index_is_stale():
    if not INDEX_PATH.exists():
        return True
    built = INDEX_PATH.stat().st_mtime
    return any(p.stat().st_mtime > built for p in POLICY_DIR.glob("*.md"))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def search(question, k=TOP_K):
    if index_is_stale():
        build_index()  # edited a policy? it gets picked up automatically
    chunks = json.loads(INDEX_PATH.read_text())["chunks"]
    q = embed([question], QUERY_PREFIX)[0]
    ranked = sorted(chunks, key=lambda c: cosine(q, c["embedding"]), reverse=True)
    return [{"source": c["source"], "section": c["section"], "text": c["text"],
             "score": round(cosine(q, c["embedding"]), 3)} for c in ranked[:k]]


# --- The tool the agent gets ------------------------------------------------

def search_policy(question: str) -> str:
    """Search the store's written policies (returns, refunds, damaged items,
    shipping, warranty, gifts). Use this for any question about what the store
    allows, how long things take, or how a process works.

    Args:
        question: The policy question in plain words, for example 'how long do refunds take'

    Returns:
        JSON list of the most relevant policy sections, each with its source file.
    """
    hits = search(question)
    return json.dumps([{k: h[k] for k in ("source", "section", "text")} for h in hits])


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build_index()
    elif sys.argv[1:]:
        question = " ".join(sys.argv[1:])
        print(f"Q: {question}\n")
        for h in search(question):
            print(f"  {h['score']:.3f}  {h['source']} > {h['section']}")
            print(f"         {h['text'][:110]}...\n")
    else:
        print(__doc__)
