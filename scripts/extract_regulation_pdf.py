from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

PDF_DIR = Path("data/regulations_pdf")
OUT_DIR = Path("data/regulations")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def infer_meta(filename: str) -> Dict[str, Any]:
    s = filename.lower()

    if "qanun" in s and "2020" in s:
        return {
            "type": "qanun",
            "title": "Qanun Aceh Nomor 1 Tahun 2020 tentang RZWP-3-K Aceh",
            "region": "Aceh",
            "year": 2020,
            "source": "Pemerintah Aceh",
        }

    if "pp" in s and "27" in s and "2021" in s:
        return {
            "type": "pp",
            "title": "PP Nomor 27 Tahun 2021 tentang Penyelenggaraan Bidang Kelautan dan Perikanan",
            "region": "Indonesia",
            "year": 2021,
            "source": "Pemerintah Republik Indonesia",
        }

    if ("36" in s and "2023" in s) or "permenkp" in s:
        return {
            "type": "permenkp",
            "title": "Permen KP Nomor 36 Tahun 2023 tentang Penempatan Alat Penangkapan Ikan dan Alat Bantu Penangkapan Ikan",
            "region": "Indonesia",
            "year": 2023,
            "source": "Kementerian Kelautan dan Perikanan",
        }

    return {
        "type": "regulasi",
        "title": filename,
        "region": "Indonesia",
        "year": None,
        "source": "Unknown",
    }


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
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
    raise RuntimeError(f"Gagal mengekstrak teks dari {pdf_path.name}")


def split_articles(text: str) -> List[Dict[str, str]]:
    # Pecah berdasarkan "Pasal <angka>" dan pertahankan judulnya
    parts = re.split(r"\b(Pasal\s+\d+[A-Za-z]?)\b", text)
    articles: List[Dict[str, str]] = []

    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        body = re.sub(r"\n\s+", "\n", body)
        body = body.strip()
        if body:
            articles.append({
                "title": title,
                "content": body,
            })

    return articles


def process_pdf(pdf_path: Path) -> Path:
    text = extract_text(pdf_path)
    articles = split_articles(text)
    meta = infer_meta(pdf_path.name)

    data = {
        "id": pdf_path.stem,
        "title": meta["title"],
        "region": meta["region"],
        "type": meta["type"],
        "year": meta["year"],
        "source": meta["source"],
        "chapters": articles,
    }

    out_path = OUT_DIR / f"{pdf_path.stem}.json"
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def process_one(pdf_str: str) -> int:
    pdf_path = Path(pdf_str)
    try:
        out = process_pdf(pdf_path)
        print(f"[OK] {pdf_path.name} -> {out}")
        return 0
    except Exception as e:
        print(f"[ERROR] {pdf_path.name}: {e}", file=sys.stderr)
        return 1


def main() -> int:
    # mode worker: proses satu file saja
    if len(sys.argv) >= 3 and sys.argv[1] == "--one":
        return process_one(sys.argv[2])

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print("Tidak ada PDF di data/regulations_pdf")
        return 1

    rc = 0
    for pdf in pdfs:
        # penting: tiap file diproses di subprocess terpisah
        proc = subprocess.run(
            [sys.executable, __file__, "--one", str(pdf)],
            check=False,
        )
        if proc.returncode != 0:
            rc = 1

    return rc


if __name__ == "__main__":
    raise SystemExit(main())