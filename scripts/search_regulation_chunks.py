from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall((text or "").lower())


def load_chunks(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix == ".jsonl":
        items = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("chunks"), list):
        return data["chunks"]
    if isinstance(data, list):
        return data
    raise ValueError("Format file chunks tidak dikenali")


def score_chunk(query_tokens: List[str], chunk: Dict[str, Any]) -> float:
    text = chunk.get("text", "")
    meta_parts = [
        chunk.get("title") or "",
        chunk.get("short_title") or "",
        chunk.get("article_label") or "",
        chunk.get("chapter") or "",
        chunk.get("section") or "",
        chunk.get("subsection") or "",
    ]
    haystack = " ".join(meta_parts) + "\n" + text
    tokens = tokenize(haystack)
    if not tokens:
        return 0.0

    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1

    score = 0.0
    for qt in query_tokens:
        c = tf.get(qt, 0)
        if c > 0:
            score += 1.0 + math.log(1 + c)

    article_label = (chunk.get("article_label") or "").lower()
    query_text = " ".join(query_tokens)
    if article_label and article_label.lower().replace(" ", "") in query_text.replace(" ", ""):
        score += 3.0

    if query_text and query_text in haystack.lower():
        score += 2.0

    return round(score, 4)


def preview(text: str, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cari pasal/chunk dari file regulasi yang sudah di-chunk.")
    p.add_argument("chunks_file", help="Path ke *.chunks.json atau *.chunks.jsonl")
    p.add_argument("query", help="Kata kunci pencarian")
    p.add_argument("-k", "--top-k", type=int, default=5, help="Jumlah hasil teratas")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.chunks_file)
    try:
        chunks = load_chunks(path)
    except Exception as e:
        print(f"Gagal membaca chunks file: {e}")
        return 1

    query_tokens = tokenize(args.query)
    if not query_tokens:
        print("Query kosong atau tidak valid")
        return 1

    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for chunk in chunks:
        s = score_chunk(query_tokens, chunk)
        if s > 0:
            ranked.append((s, chunk))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top = ranked[: args.top_k]

    if not top:
        print("Tidak ada hasil yang cocok.")
        return 0

    for i, (score, chunk) in enumerate(top, start=1):
        print("=" * 80)
        print(f"#{i} | score={score}")
        print(f"Regulasi : {chunk.get('short_title') or chunk.get('title')}")
        print(f"Pasal    : {chunk.get('article_label') or '-'}")
        print(f"Tipe     : {chunk.get('chunk_type')}")
        print(f"Chunk ID : {chunk.get('chunk_id')}")
        print(f"Preview  : {preview(chunk.get('text', ''))}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
