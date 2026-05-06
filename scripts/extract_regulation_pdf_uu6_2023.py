from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_OUT_DIR = Path("data/regulations_pdf")


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_with_pdftotext(pdf_path: Path) -> Optional[str]:
    exe = shutil.which("pdftotext")
    if not exe:
        return None

    try:
        proc = subprocess.run(
            [exe, "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return normalize_text(proc.stdout)
    except Exception:
        return None
    return None


def extract_with_pymupdf(pdf_path: Path) -> Optional[str]:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None

    try:
        doc = fitz.open(str(pdf_path))
        parts: List[str] = []
        for page in doc:
            t = page.get_text("text") or ""
            if t.strip():
                parts.append(t)
        doc.close()
        text = "\n".join(parts)
        return normalize_text(text) if text.strip() else None
    except Exception:
        return None


def extract_with_pypdf(pdf_path: Path) -> Optional[str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return None

    try:
        reader = PdfReader(str(pdf_path))
        parts: List[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t)
        text = "\n".join(parts)
        return normalize_text(text) if text.strip() else None
    except Exception:
        return None


def extract_text(pdf_path: Path) -> str:
    for fn in (extract_with_pdftotext, extract_with_pymupdf, extract_with_pypdf):
        text = fn(pdf_path)
        if text:
            return text
    raise RuntimeError(
        f"Gagal mengekstrak teks dari {pdf_path.name}. Jika PDF hasil scan gambar, perlu OCR."
    )


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def infer_meta(filename: str, text: str) -> Dict[str, Any]:
    s = filename.lower()
    t = text.lower()

    if (
        ("uu" in s and "6" in s and "2023" in s)
        or "undang-undang nomor 6 tahun 2023" in t
        or "undang-undang (uu) nomor 6 tahun 2023" in t
    ):
        return {
            "type": "uu",
            "number": 6,
            "year": 2023,
            "title": "Undang-Undang Nomor 6 Tahun 2023 tentang Penetapan Peraturan Pemerintah Pengganti Undang-Undang Nomor 2 Tahun 2022 tentang Cipta Kerja menjadi Undang-Undang",
            "short_title": "UU No. 6 Tahun 2023",
            "topic": "Cipta Kerja",
            "region": "Indonesia",
            "source": "Pemerintah Republik Indonesia",
        }

    if "qanun" in s and "2020" in s:
        return {
            "type": "qanun",
            "number": 1,
            "year": 2020,
            "title": "Qanun Aceh Nomor 1 Tahun 2020 tentang RZWP-3-K Aceh",
            "short_title": "Qanun Aceh No. 1 Tahun 2020",
            "topic": "RZWP-3-K Aceh",
            "region": "Aceh",
            "source": "Pemerintah Aceh",
        }

    if "pp" in s and "27" in s and "2021" in s:
        return {
            "type": "pp",
            "number": 27,
            "year": 2021,
            "title": "PP Nomor 27 Tahun 2021 tentang Penyelenggaraan Bidang Kelautan dan Perikanan",
            "short_title": "PP No. 27 Tahun 2021",
            "topic": "Penyelenggaraan Bidang Kelautan dan Perikanan",
            "region": "Indonesia",
            "source": "Pemerintah Republik Indonesia",
        }

    if ("36" in s and "2023" in s) or "permenkp" in s:
        return {
            "type": "permenkp",
            "number": 36,
            "year": 2023,
            "title": "Permen KP Nomor 36 Tahun 2023 tentang Penempatan Alat Penangkapan Ikan dan Alat Bantu Penangkapan Ikan",
            "short_title": "Permen KP No. 36 Tahun 2023",
            "topic": "Penempatan Alat Penangkapan Ikan dan Alat Bantu Penangkapan Ikan",
            "region": "Indonesia",
            "source": "Kementerian Kelautan dan Perikanan",
        }

    return {
        "type": "regulasi",
        "number": None,
        "year": None,
        "title": filename,
        "short_title": filename,
        "topic": None,
        "region": "Indonesia",
        "source": "Unknown",
    }


def extract_considering(text: str) -> str:
    m = re.search(r"Menimbang\s*:(.*?)(?=Mengingat\s*:)", text, flags=re.S | re.I)
    return normalize_text(m.group(1)) if m else ""


def extract_references(text: str) -> List[str]:
    m = re.search(r"Mengingat\s*:(.*?)(?=Dengan Persetujuan Bersama|MEMUTUSKAN:)", text, flags=re.S | re.I)
    if not m:
        return []

    block = normalize_text(m.group(1))
    refs = re.split(r"\n\s*\d+\.\s+", "\n" + block)
    refs = [normalize_text(x) for x in refs if normalize_text(x)]
    return refs


def extract_decision_intro(text: str) -> str:
    m = re.search(r"MEMUTUSKAN\s*:(.*?)(?=\bBAB\s+[IVXLCDM]+\b|\bPasal\s+1\b)", text, flags=re.S | re.I)
    return normalize_text(m.group(1)) if m else ""


def find_article_spans(text: str) -> List[Tuple[re.Match[str], int, int]]:
    matches = list(re.finditer(r"(?m)^\s*(Pasal\s+(\d+[A-Za-z]?))\s*$", text))
    spans: List[Tuple[re.Match[str], int, int]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((m, start, end))
    return spans


def nearest_heading(before_text: str, pattern: str) -> Optional[str]:
    matches = list(re.finditer(pattern, before_text, flags=re.M))
    if not matches:
        return None
    return normalize_text(matches[-1].group(0))


def split_articles(text: str) -> List[Dict[str, Any]]:
    spans = find_article_spans(text)
    articles: List[Dict[str, Any]] = []

    for m, start, end in spans:
        article_label = m.group(1).strip()
        article_no = m.group(2).strip()
        block = text[m.end():end].strip()
        block = re.sub(r"\n\s+", "\n", block)
        block = normalize_text(block)

        prefix = text[:start]
        bab = nearest_heading(prefix, r"^\s*BAB\s+[IVXLCDM]+\s*$")
        bagian = nearest_heading(prefix, r"^\s*Bagian\s+[A-Za-z0-9 .-]+$")
        paragraf = nearest_heading(prefix, r"^\s*Paragraf\s+[0-9A-Za-z .-]+$")

        articles.append(
            {
                "article_number": article_no,
                "article_label": article_label,
                "chapter": bab,
                "section": bagian,
                "subsection": paragraf,
                "content": block,
            }
        )

    return articles


def extract_title_from_text(text: str) -> Optional[str]:
    m = re.search(
        r"UNDANG-UNDANG\s+REPUBLIK\s+INDONESIA\s+NOMOR\s+\d+\s+TAHUN\s+\d{4}\s+TENTANG\s+(.+?)(?=DENGAN\s+RAHMAT|PRESIDEN\s+REPUBLIK\s+INDONESIA)",
        text,
        flags=re.S | re.I,
    )
    if not m:
        return None
    tentang = normalize_text(m.group(1))
    return tentang


def build_json(pdf_path: Path, text: str) -> Dict[str, Any]:
    meta = infer_meta(pdf_path.name, text)
    title_from_text = extract_title_from_text(text)
    if title_from_text and meta["type"] == "regulasi":
        meta["title"] = f"Regulasi tentang {title_from_text}"

    articles = split_articles(text)
    considering = extract_considering(text)
    references = extract_references(text)
    decision_intro = extract_decision_intro(text)

    return {
        "id": slugify(pdf_path.stem),
        "file_name": pdf_path.name,
        "source_pdf": str(pdf_path),
        "title": meta["title"],
        "short_title": meta.get("short_title"),
        "topic": meta.get("topic"),
        "region": meta["region"],
        "type": meta["type"],
        "number": meta.get("number"),
        "year": meta["year"],
        "source": meta["source"],
        "stats": {
            "article_count": len(articles),
            "has_considering": bool(considering),
            "references_count": len(references),
        },
        "preamble": {
            "considering": considering,
            "references": references,
            "decision_intro": decision_intro,
        },
        "articles": articles,
        "full_text": text,
    }


def process_pdf(pdf_path: Path, out_dir: Path) -> Path:
    text = extract_text(pdf_path)
    data = build_json(pdf_path, text)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pdf_path.stem}.json"
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ekstrak PDF regulasi menjadi JSON terstruktur."
    )
    parser.add_argument("pdf", type=str, help="Path ke file PDF")
    parser.add_argument(
        "-o",
        "--out-dir",
        type=str,
        default=str(DEFAULT_OUT_DIR),
        help="Folder output JSON",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"File tidak ditemukan: {pdf_path}")

    out_dir = Path(args.out_dir)
    out_path = process_pdf(pdf_path, out_dir)
    print(f"[OK] {pdf_path.name} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
