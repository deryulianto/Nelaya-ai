from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


AYAT_RE = re.compile(r"(?=(\(\d+\)))")
LIST_ALPHA_RE = re.compile(r"(?=(?<!\w)([a-z])\.(?=\s))")
LIST_NUM_RE = re.compile(r"(?=(?<!\w)(\d+)\.(?=\s))")
WS_RE = re.compile(r"[ \t]+")
NL3_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = WS_RE.sub(" ", text)
    text = NL3_RE.sub("\n\n", text)
    return text.strip()


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "chunk"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_articles(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_articles = data.get("articles")
    if isinstance(raw_articles, list) and raw_articles:
        return raw_articles

    raw_chapters = data.get("chapters")
    if isinstance(raw_chapters, list) and raw_chapters:
        normalized: List[Dict[str, Any]] = []
        for item in raw_chapters:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "article_label": item.get("title") or item.get("article_label"),
                    "article_number": extract_article_number(item.get("title") or item.get("article_label") or ""),
                    "content": item.get("content", ""),
                    "chapter": item.get("chapter"),
                    "section": item.get("section"),
                    "subsection": item.get("subsection"),
                }
            )
        return normalized

    return []


def extract_article_number(label: str) -> Optional[str]:
    m = re.search(r"Pasal\s+([0-9]+[A-Za-z]?)", label or "", flags=re.IGNORECASE)
    return m.group(1) if m else None


def split_ayat(text: str) -> List[Tuple[str, str]]:
    text = normalize_text(text)
    if not text:
        return []

    markers = list(re.finditer(r"\((\d+)\)", text))
    if not markers:
        return []

    chunks: List[Tuple[str, str]] = []
    for i, m in enumerate(markers):
        start = m.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        label = m.group(0)
        part = text[start:end].strip()
        if part:
            chunks.append((label, part))
    return chunks


def split_letter_items(text: str) -> List[Tuple[str, str]]:
    text = normalize_text(text)
    if not text:
        return []

    markers = list(re.finditer(r"(?<!\w)([a-z])\.(?=\s)", text))
    if len(markers) < 2:
        return []

    chunks: List[Tuple[str, str]] = []
    for i, m in enumerate(markers):
        start = m.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        label = f"{m.group(1)}."
        part = text[start:end].strip()
        if part:
            chunks.append((label, part))
    return chunks


def split_paragraph_windows(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    windows: List[str] = []
    buf = ""

    for para in paragraphs:
        candidate = para if not buf else f"{buf}\n\n{para}"
        if len(candidate) <= max_chars:
            buf = candidate
            continue

        if buf:
            windows.append(buf.strip())
            tail = buf[-overlap:] if overlap > 0 else ""
            buf = f"{tail}\n\n{para}".strip()
            if len(buf) <= max_chars:
                continue

        if len(para) <= max_chars:
            windows.append(para)
            buf = ""
            continue

        step = max(1, max_chars - overlap)
        for idx in range(0, len(para), step):
            piece = para[idx: idx + max_chars].strip()
            if piece:
                windows.append(piece)
        buf = ""

    if buf.strip():
        windows.append(buf.strip())

    return windows


def build_base_meta(data: Dict[str, Any], src_path: Path) -> Dict[str, Any]:
    return {
        "regulation_id": data.get("id") or slugify(src_path.stem),
        "source_json": str(src_path),
        "file_name": src_path.name,
        "title": data.get("title"),
        "short_title": data.get("short_title"),
        "topic": data.get("topic"),
        "type": data.get("type"),
        "number": data.get("number"),
        "year": data.get("year"),
        "region": data.get("region"),
        "source": data.get("source"),
    }


def chunk_article(
    article: Dict[str, Any],
    base_meta: Dict[str, Any],
    max_chars: int,
    overlap: int,
) -> List[Dict[str, Any]]:
    label = article.get("article_label") or article.get("title") or "Pasal"
    article_number = article.get("article_number") or extract_article_number(label)
    content = normalize_text(article.get("content", ""))
    chapter = article.get("chapter")
    section = article.get("section")
    subsection = article.get("subsection")

    common = {
        **base_meta,
        "article_number": article_number,
        "article_label": label,
        "chapter": chapter,
        "section": section,
        "subsection": subsection,
    }

    out: List[Dict[str, Any]] = []

    ayat_parts = split_ayat(content)
    if ayat_parts:
        for idx, (ayat_label, text) in enumerate(ayat_parts, start=1):
            out.append(
                {
                    **common,
                    "chunk_id": f"{base_meta['regulation_id']}::pasal-{article_number or slugify(label)}::ayat-{slugify(ayat_label)}",
                    "chunk_type": "ayat",
                    "chunk_index": idx,
                    "ayat_label": ayat_label,
                    "text": text,
                }
            )
        return out

    letter_parts = split_letter_items(content)
    if letter_parts:
        for idx, (item_label, text) in enumerate(letter_parts, start=1):
            out.append(
                {
                    **common,
                    "chunk_id": f"{base_meta['regulation_id']}::pasal-{article_number or slugify(label)}::item-{slugify(item_label)}",
                    "chunk_type": "list_item",
                    "chunk_index": idx,
                    "item_label": item_label,
                    "text": text,
                }
            )
        return out

    windows = split_paragraph_windows(content, max_chars=max_chars, overlap=overlap)
    if not windows and content:
        windows = [content]

    for idx, text in enumerate(windows, start=1):
        out.append(
            {
                **common,
                "chunk_id": f"{base_meta['regulation_id']}::pasal-{article_number or slugify(label)}::chunk-{idx:03d}",
                "chunk_type": "article_chunk" if len(windows) > 1 else "article",
                "chunk_index": idx,
                "text": text,
            }
        )

    return out


def chunk_regulation(data: Dict[str, Any], src_path: Path, max_chars: int, overlap: int) -> Dict[str, Any]:
    articles = get_articles(data)
    base_meta = build_base_meta(data, src_path)

    chunks: List[Dict[str, Any]] = []
    for art in articles:
        chunks.extend(chunk_article(art, base_meta, max_chars=max_chars, overlap=overlap))

    preamble = data.get("preamble") or {}
    if isinstance(preamble, dict):
        preamble_texts: List[Tuple[str, str]] = []
        if preamble.get("considering"):
            preamble_texts.append(("considering", normalize_text(str(preamble["considering"]))))
        refs = preamble.get("references")
        if isinstance(refs, list) and refs:
            preamble_texts.append(("references", normalize_text("\n".join(str(x) for x in refs if x))))
        if preamble.get("decision_intro"):
            preamble_texts.append(("decision_intro", normalize_text(str(preamble["decision_intro"]))))

        for idx, (kind, text) in enumerate(preamble_texts, start=1):
            if text:
                chunks.append(
                    {
                        **base_meta,
                        "article_number": None,
                        "article_label": None,
                        "chapter": None,
                        "section": None,
                        "subsection": None,
                        "chunk_id": f"{base_meta['regulation_id']}::preamble::{kind}",
                        "chunk_type": f"preamble_{kind}",
                        "chunk_index": idx,
                        "text": text,
                    }
                )

    stats = {
        "source_json": str(src_path),
        "article_count": len(articles),
        "chunk_count": len(chunks),
        "avg_chunk_length": round(sum(len(c["text"]) for c in chunks) / len(chunks), 2) if chunks else 0,
        "max_chunk_length": max((len(c["text"]) for c in chunks), default=0),
    }

    return {
        "meta": base_meta,
        "stats": stats,
        "chunks": chunks,
    }


def write_outputs(result: Dict[str, Any], out_dir: Path, stem: str) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.chunks.json"
    jsonl_path = out_dir / f"{stem}.chunks.jsonl"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for chunk in result["chunks"]:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return json_path, jsonl_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Chunk JSON regulasi menjadi unit siap-RAG/search.")
    p.add_argument("input_json", help="Path file JSON regulasi hasil ekstraksi")
    p.add_argument("-o", "--out-dir", default="data/regulations_chunks", help="Folder output")
    p.add_argument("--max-chars", type=int, default=1200, help="Maksimum panjang chunk untuk fallback paragraph window")
    p.add_argument("--overlap", type=int, default=150, help="Overlap karakter antar chunk fallback")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    src = Path(args.input_json)
    if not src.exists():
        print(f"File JSON tidak ditemukan: {src}")
        return 1

    data = load_json(src)
    result = chunk_regulation(data, src, max_chars=args.max_chars, overlap=args.overlap)
    json_path, jsonl_path = write_outputs(result, Path(args.out_dir), src.stem)

    print(f"[OK] JSON chunks : {json_path}")
    print(f"[OK] JSONL chunks: {jsonl_path}")
    print(json.dumps(result["stats"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
