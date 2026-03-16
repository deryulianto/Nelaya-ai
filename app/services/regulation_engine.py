from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any, Dict, List, Tuple

REG_DIR = Path("data/regulations")


# =========================
# Text utilities
# =========================

def _normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _tokenize(text: str) -> List[str]:
    text = _normalize(text)
    text = re.sub(r"[^a-zA-Z0-9à-ÿ_\-\s]", " ", text)
    return [t for t in text.split() if len(t) >= 2]


def _make_snippet(text: str, max_len: int = 340) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _unique_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _clean_artifact_lines(text: str) -> str:
    lines = (text or "").splitlines()
    kept: List[str] = []

    artifact_patterns = [
        r"^\s*sk no\b",
        r"^\s*pres iden\b",
        r"^\s*presiden\b",
        r"^\s*republik indonesia\b",
        r"^\s*-\s*\d+\s*-\s*$",
        r"^\s*\d+\s*$",
    ]

    for line in lines:
        ln = line.strip()
        low = ln.lower()
        if not ln:
            kept.append("")
            continue

        if any(re.search(p, low) for p in artifact_patterns):
            continue

        # angka artefak seperti 086611 A / 086621 A
        if re.fullmatch(r"\d{5,}\s*[A-Z]?", ln):
            continue

        kept.append(line)

    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _extract_number_candidates(text: str) -> List[str]:
    clean = _clean_artifact_lines(text)
    nums = re.findall(r"\b\d+(?:[\.,]\d+)?\b", clean)

    filtered: List[str] = []
    for n in nums:
        # buang angka artefak terlalu panjang seperti nomor SK
        pure = n.replace(".", "").replace(",", "")
        if len(pure) >= 5:
            continue
        filtered.append(n)

    return filtered


# =========================
# Query understanding
# =========================

def classify_regulation_query(query: str) -> str:
    q = _normalize(query)

    if "apa itu" in q or "pengertian" in q or q.startswith("definisi "):
        return "definition_query"

    if "sebutkan" in q or "apa saja" in q or "jenis" in q or "daftar" in q:
        if "alat tangkap" in q or "api" in q:
            return "gear_query"
        return "list_query"

    if "berapa" in q or "jumlah" in q or "ada berapa" in q:
        if "zona" in q or "jalur" in q:
            return "zoning_query"
        if "jarak" in q and "rumpon" in q:
            return "distance_query"
        return "count_query"

    if "rumpon" in q:
        if "jarak" in q:
            return "distance_query"
        if "izin" in q or "sipr" in q:
            return "license_query"
        if "dimana" in q or "di mana" in q or "ditempatkan" in q or "penempatan" in q:
            return "placement_query"
        if "boleh" in q or "tidak boleh" in q:
            return "permission_query"
        return "rumpon_query"

    if "alat tangkap" in q or "api" in q:
        if "dilarang" in q or "larangan" in q:
            return "forbidden_gear_query"
        if "boleh" in q or "diperbolehkan" in q:
            return "allowed_gear_query"
        return "gear_query"

    if "wppnri" in q:
        return "wppnri_query"

    if "jalur penangkapan" in q:
        return "route_query"

    if "zona penangkapan" in q or ("zona" in q and "ikan" in q):
        if "aceh" in q:
            return "zoning_aceh_query"
        return "zoning_query"

    if "izin" in q or "perizinan" in q:
        return "license_query"

    if "boleh" in q or "diperbolehkan" in q or "tidak boleh" in q:
        return "permission_query"

    if "dilarang" in q or "larangan" in q:
        return "prohibition_query"

    if "syarat" in q or "persyaratan" in q:
        return "requirement_query"

    if "wajib" in q or "kewajiban" in q:
        return "obligation_query"

    if "cara" in q or "prosedur" in q or "mekanisme" in q:
        return "procedure_query"

    if "dimana" in q or "di mana" in q or "lokasi" in q:
        return "location_query"

    if "ditempatkan" in q or "penempatan" in q:
        return "placement_query"

    if "siapa yang berwenang" in q or "kewenangan" in q or "otoritas" in q:
        return "authority_query"

    if "sanksi" in q or "hukuman" in q:
        return "sanction_query"

    if "konservasi" in q or "kawasan konservasi" in q:
        return "conservation_query"

    if "nelayan kecil" in q:
        return "small_fisher_query"

    if "ruang lingkup" in q or "cakupan" in q:
        return "scope_query"

    if "teknis" in q or "spesifikasi" in q:
        return "technical_query"

    if "dokumen" in q or "aturan apa" in q:
        return "document_query"
   
    if "panglima laot" in q or "adat laut" in q:
        return "institution_query"

    return "general_query"


def detect_topics(query: str) -> List[str]:
    q = _normalize(query)
    topics: List[str] = []

    topic_map = {
        "rumpon": ["rumpon", "sipr", "atraktor"],
        "zona_penangkapan": ["zona penangkapan", "jalur penangkapan", "wppnri", "laut lepas"],
        "alat_tangkap": ["alat tangkap", "api", "abpi", "jaring", "pancing", "bubu", "bagan", "rawai", "pukat"],
        "izin": ["izin", "perizinan", "sipr"],
        "larangan": ["dilarang", "larangan", "tidak boleh"],
        "jarak": ["jarak", "mil laut", "paling dekat"],
        "konservasi": ["konservasi", "kawasan konservasi"],
        "nelayan_kecil": ["nelayan kecil"],
        "aceh": ["aceh", "banda aceh", "aceh besar", "sabang", "simeulue", "simeuleu", "pulau weh"],
        "wppnri_571_572": ["wppnri 571", "wppnri 572", "selat malaka", "laut andaman", "samudera hindia"],
        "jalur": ["jalur i", "jalur ii", "jalur iii", "jalur penangkapan"],
        "kewenangan": ["berwenang", "kewenangan", "otoritas", "menteri", "gubernur"],
        "sanksi": ["sanksi", "hukuman"],
        "panglima_laot": ["panglima laot", "panglima laot lhok", "adat laut", "masyarakat hukum adat laut", "wilayah kelola masyarakat hukum adat laut"], 
    }

    for topic, keys in topic_map.items():
        if any(k in q for k in keys):
            topics.append(topic)

    return topics


def expand_query(query: str, query_type: str, topics: List[str]) -> List[str]:
    q = _normalize(query)
    expanded = [q]

    if "aceh" in q or "aceh" in topics:
        expanded.extend([
            "aceh",
            "wppnri 571",
            "wppnri 572",
            "selat malaka",
            "laut andaman",
            "samudera hindia sebelah barat sumatera",
            "pulau weh",
            "simeuleu",
            "simeulue",
        ])

    if query_type in {"zoning_query", "route_query", "wppnri_query", "zoning_aceh_query"}:
        expanded.extend([
            "zona penangkapan ikan terukur",
            "jalur penangkapan ikan",
            "wppnri",
            "laut lepas",
            "zona 01",
            "zona 02",
            "zona 03",
            "zona 04",
            "zona 05",
            "zona 06",
            "jalur penangkapan ikan i",
            "jalur penangkapan ikan ii",
            "jalur penangkapan ikan iii",
        ])

    if "rumpon" in topics or query_type in {"rumpon_query", "distance_query", "license_query", "placement_query"}:
        expanded.extend([
            "rumpon",
            "sipr",
            "rumpon hanyut",
            "rumpon menetap",
            "jarak antar rumpon",
            "kawasan konservasi",
            "alur laut kepulauan indonesia",
            "alur migrasi penyu dan mamalia laut",
        ])

    if "alat_tangkap" in topics or query_type in {"gear_query", "allowed_gear_query", "forbidden_gear_query", "list_query"}:
        expanded.extend([
            "alat penangkapan ikan",
            "api",
            "abpi",
            "api yang diperbolehkan",
            "api yang dilarang",
            "jaring lingkar",
            "jaring tarik",
            "jaring hela",
            "jaring insang",
            "perangkap",
            "pancing",
            "api lainnya",
        ])

    if "panglima_laot" in topics or query_type == "institution_query":
        expanded.extend([
            "panglima laot",
            "panglima laot lhok",
            "masyarakat hukum adat laut",
            "wilayah kelola masyarakat hukum adat laut",
            "wewenang tugas dan fungsi",
            "qanun aceh",
        ]) 

    if query_type in {"permission_query", "license_query", "requirement_query", "obligation_query"}:
        expanded.extend([
            "izin",
            "perizinan",
            "boleh",
            "diperbolehkan",
            "tidak boleh",
            "wajib",
            "persyaratan",
        ])

    return _unique_keep_order(expanded)


# =========================
# Engine
# =========================

class RegulationEngine:
    def __init__(self) -> None:
        self.docs: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        self.docs = []
        for f in sorted(REG_DIR.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                self.docs.append(data)
            except Exception:
                continue

    def stats(self) -> Dict[str, Any]:
        n_articles = sum(len(doc.get("chapters", [])) for doc in self.docs)
        return {
            "documents": len(self.docs),
            "articles": n_articles,
        }

    def _find_doc_title(self, contains: str) -> str:
        target = contains.lower()
        for doc in self.docs:
            title = str(doc.get("title", ""))
            if target in title.lower():
                return title
        return ""

    def _specialized_search_rumpon_distance(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        for doc in self.docs:
            title = str(doc.get("title", ""))
            if "permen kp nomor 36 tahun 2023" not in title.lower():
                continue

            for ch in doc.get("chapters", []):
                pasal = str(ch.get("title", ""))
                text = _clean_artifact_lines(str(ch.get("content", "")))
                low = text.lower()

                if "rumpon" in low and "jarak" in low and "mil laut" in low:
                    out.append({
                        "title": title,
                        "pasal": pasal,
                        "snippet": _make_snippet(text),
                        "text": text[:2000],
                        "score": 999,
                    })

        return out[:5]

    def _specialized_search_forbidden_gear(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        for doc in self.docs:
            title = str(doc.get("title", ""))
            if "permen kp nomor 36 tahun 2023" not in title.lower():
                continue

            for ch in doc.get("chapters", []):
                pasal = str(ch.get("title", ""))
                text = _clean_artifact_lines(str(ch.get("content", "")))
                low = text.lower()

                if (
                    "api yang dilarang" in low
                    or "jenis api yang dilarang" in low
                    or ("dilarang" in low and ("cantrang" in low or "dogol" in low or "pukat harimau" in low))
                ):
                    out.append({
                        "title": title,
                        "pasal": pasal,
                        "snippet": _make_snippet(text),
                        "text": text[:2200],
                        "score": 999,
                    })

        return out[:5]

    def _score_result(
        self,
        query: str,
        query_type: str,
        topics: List[str],
        title: str,
        pasal: str,
        content: str,
    ) -> int:
        score = 0

        q_tokens = set(_tokenize(query))
        hay = _normalize(f"{title} {pasal} {content}")
        hay_tokens = set(_tokenize(hay))

        score += len(q_tokens & hay_tokens)

        if pasal.strip().lower() == "pasal 1" and query_type not in {"definition_query", "scope_query"}:
            score -= 4

        if query in hay:
            score += 6

        title_l = title.lower()

        if query_type in {"zoning_query", "route_query", "wppnri_query", "zoning_aceh_query"}:
            for term in [
                "zona penangkapan ikan terukur",
                "jalur penangkapan ikan",
                "wppnri",
                "laut lepas",
                "zona 01", "zona 02", "zona 03", "zona 04", "zona 05", "zona 06",
            ]:
                if term in hay:
                    score += 3
            if "permen kp nomor 36 tahun 2023" in title_l:
                score += 5

        if query_type in {"rumpon_query", "distance_query", "license_query", "placement_query"}:
            for term in [
                "rumpon",
                "sipr",
                "rumpon menetap",
                "rumpon hanyut",
                "jarak antar rumpon",
                "kawasan konservasi",
                "mil laut",
            ]:
                if term in hay:
                    score += 4
            if "permen kp nomor 36 tahun 2023" in title_l:
                score += 8

        if query_type in {"gear_query", "allowed_gear_query", "forbidden_gear_query", "list_query"}:
            for term in [
                "alat penangkapan ikan",
                "api yang diperbolehkan",
                "api yang dilarang",
                "jaring lingkar",
                "jaring tarik",
                "jaring hela",
                "jaring insang",
                "perangkap",
                "pancing",
                "api lainnya",
            ]:
                if term in hay:
                    score += 3
            if "permen kp nomor 36 tahun 2023" in title_l:
                score += 7

        if query_type in {"permission_query", "prohibition_query", "requirement_query", "obligation_query"}:
            for term in ["dilarang", "boleh", "diperbolehkan", "izin", "persyaratan", "wajib"]:
                if term in hay:
                    score += 2

        if "aceh" in topics and "qanun aceh" in title_l:
            score += 2

        if "wppnri_571_572" in topics and "permen kp nomor 36 tahun 2023" in title_l:
            score += 3

        return score

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query_type = classify_regulation_query(query)
        topics = detect_topics(query)

        # hard-route domain kritis v3.1
        if query_type == "distance_query" and "rumpon" in _normalize(query):
            special = self._specialized_search_rumpon_distance()
            if special:
                return special[:top_k]

        if query_type in {"forbidden_gear_query", "prohibition_query"} and ("alat tangkap" in _normalize(query) or "api" in _normalize(query)):
            special = self._specialized_search_forbidden_gear()
            if special:
                return special[:top_k]

        expanded_queries = expand_query(query, query_type, topics)
        scored: List[Tuple[int, Dict[str, Any]]] = []

        for doc in self.docs:
            title = doc.get("title", "")
            for ch in doc.get("chapters", []):
                pasal = ch.get("title", "")
                content = _clean_artifact_lines(str(ch.get("content", "")))

                best_score = 0
                for eq in expanded_queries:
                    s = self._score_result(eq, query_type, topics, title, pasal, content)
                    if s > best_score:
                        best_score = s

                if best_score <= 0:
                    continue

                scored.append(
                    (
                        best_score,
                        {
                            "title": title,
                            "pasal": pasal,
                            "snippet": _make_snippet(content),
                            "text": content[:2200],
                            "score": best_score,
                        },
                    )
                )

        scored.sort(key=lambda x: x[0], reverse=True)

        dedup: List[Dict[str, Any]] = []
        seen = set()
        for _, item in scored:
            key = (item["title"], item["pasal"])
            if key in seen:
                continue
            seen.add(key)
            dedup.append(item)
            if len(dedup) >= top_k:
                break

        return dedup

    # -------------------------
    # specialized answer builders
    # -------------------------

    def _answer_definition(self, query: str, results: List[Dict[str, Any]]) -> str:
        top = results[0]
        return (
            f"Berdasarkan {top['title']} {top['pasal']}, terdapat definisi atau ketentuan umum yang relevan. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_zoning(self, query: str, results: List[Dict[str, Any]], topics: List[str]) -> str:
        q = _normalize(query)

        if "aceh" in q and ("zona penangkapan" in q or "jalur penangkapan" in q):
            return (
                "Dalam pengaturan nasional penangkapan ikan terukur, zona penangkapan ikan dibagi menjadi 6 zona. "
                "Untuk wilayah Aceh, yang paling relevan adalah zona 05 yang mencakup WPPNRI 571 "
                "(Selat Malaka dan Laut Andaman), serta zona 04 yang mencakup WPPNRI 572 "
                "(Samudera Hindia sebelah barat Sumatera). "
                "Jika yang dimaksud adalah tata ruang laut Aceh, maka rujukan utamanya adalah Qanun Aceh No. 1 Tahun 2020 "
                "tentang RZWP-3-K Aceh, yang mengatur zona perikanan tangkap sebagai bagian dari alokasi ruang laut Aceh."
            )

        top = results[0]
        return (
            f"Ketentuan zonasi yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_distance(self, query: str, results: List[Dict[str, Any]]) -> str:
        q = _normalize(query)
        top = results[0]
        clean = _clean_artifact_lines(top["text"])
        low = clean.lower()

        if "rumpon" in q:
            if "10" in _extract_number_candidates(clean) and "mil laut" in low:
                return (
                    "Untuk rumpon menetap di WPPNRI PL, jarak antar rumpon pada Jalur Penangkapan Ikan II dan III "
                    "paling dekat adalah 10 mil laut. Selain itu, rumpon tidak boleh ditempatkan di kawasan konservasi, "
                    "alur laut kepulauan Indonesia, alur migrasi penyu dan mamalia laut, alur pelayaran keluar masuk pelabuhan, "
                    "serta kawasan ekosistem terumbu karang."
                )

        nums = _extract_number_candidates(clean)
        if nums:
            return (
                f"Ketentuan jarak yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
                f"Angka yang paling menonjol dari hasil pembacaan awal adalah {', '.join(nums[:5])}. "
                f"Silakan cek pasal sumber untuk memastikan konteks angka tersebut."
            )

        return (
            f"Ketentuan jarak yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_permission(self, query: str, results: List[Dict[str, Any]]) -> str:
        top = results[0]
        return (
            f"Dari pembacaan awal regulasi, jawaban paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_prohibition(self, query: str, results: List[Dict[str, Any]]) -> str:
        q = _normalize(query)
        joined = " ".join(_clean_artifact_lines(r["text"]).lower() for r in results[:3])

        if "alat tangkap" in q or "api" in q:
            forbidden = [
                "dogol",
                "pair seine",
                "cantrang",
                "lampara dasar",
                "pukat hela dasar berpalang",
                "pukat hela dasar udang",
                "pukat hela kembar berpapan",
                "pukat hela dasar dua kapal",
                "pukat hela pertengahan dua kapal",
                "pukat ikan",
                "pukat harimau",
                "perangkap ikan peloncat",
                "muro ami",
            ]
            found = [x for x in forbidden if x in joined]
            found = _unique_keep_order(found)

            if found:
                return (
                    "Berdasarkan regulasi yang telah diindeks, beberapa alat tangkap yang dilarang antara lain: "
                    + ", ".join(found[:10])
                    + ". Selain itu, penangkapan ikan juga dilarang menggunakan bahan kimia, bahan biologis, bahan peledak, racun, listrik, "
                      "atau cara lain yang merugikan kelestarian sumber daya ikan dan lingkungannya."
                )

        top = results[0]
        return (
            f"Larangan yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_license(self, query: str, results: List[Dict[str, Any]]) -> str:
        top = results[0]
        return (
            f"Ketentuan terkait izin atau perizinan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_gear_list(self, query: str, results: List[Dict[str, Any]]) -> str:
        joined = " ".join(_clean_artifact_lines(r["text"]).lower() for r in results[:3])

        candidates = [
            "jaring lingkar",
            "jaring tarik",
            "jaring hela",
            "penggaruk",
            "jaring angkat",
            "alat yang dijatuhkan atau ditebarkan",
            "jaring insang",
            "perangkap",
            "pancing",
            "api lainnya",
            "pukat cincin",
            "rawai",
            "bubu",
            "bagan",
            "pancing ulur",
        ]

        found = [c for c in candidates if c in joined]
        found = _unique_keep_order(found)

        if found:
            return (
                "Berdasarkan regulasi yang telah diindeks, beberapa kelompok atau jenis alat tangkap yang paling relevan "
                f"antara lain: {', '.join(found[:8])}. Untuk rincian lengkap, rujukan utamanya adalah Permen KP No. 36 Tahun 2023 "
                "yang mengelompokkan API ke dalam beberapa kelompok besar beserta klasifikasi alat yang diperbolehkan dan dilarang."
            )

        top = results[0]
        return (
            f"Daftar alat tangkap yang paling relevan belum bisa dirangkum sempurna, tetapi rujukan terdekat ditemukan pada "
            f"{top['title']} {top['pasal']}. Intinya, {top['snippet']}"
        )

    def _answer_count(self, query: str, results: List[Dict[str, Any]]) -> str:
        q = _normalize(query)

        if "zona" in q and "aceh" in q:
            return self._answer_zoning(query, results, detect_topics(query))

        top = results[0]
        nums = _extract_number_candidates(top["text"])
        if nums:
            return (
                f"Ketentuan yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
                f"Angka yang paling menonjol dari hasil pembacaan awal adalah {', '.join(nums[:5])}. "
                f"Silakan cek pasal sumber untuk memastikan konteks angka tersebut."
            )

        return (
            f"Ketentuan yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Namun, jawaban berbentuk jumlah/angka belum dapat dipastikan hanya dari potongan ini."
        )

    def _answer_authority(self, query: str, results: List[Dict[str, Any]]) -> str:
        top = results[0]
        return (
            f"Dari basis regulasi yang tersedia, kewenangan paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_general(self, query: str, results: List[Dict[str, Any]]) -> str:
        top = results[0]
        return (
            f"Ketentuan yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def _answer_institution(self, query: str, results: List[Dict[str, Any]]) -> str:
        q = _normalize(query)

        if "panglima laot" in q:
            return (
                "Berdasarkan Qanun Aceh No. 1 Tahun 2020 tentang RZWP-3-K Aceh, "
                "Panglima Laot adalah orang yang memimpin dan mengatur adat-istiadat "
                "di bidang pesisir dan kelautan. Qanun ini juga mengakui Panglima Laot Lhok "
                "sebagai pemimpin adat di tingkat lhok, serta menegaskan bahwa wilayah kelola "
                "Masyarakat Hukum Adat Laut dilaksanakan oleh Panglima Laot sesuai wewenang, "
                "tugas, dan fungsinya berdasarkan qanun yang mengaturnya."
            )

        top = results[0]
        return (
            f"Kelembagaan adat yang paling relevan ditemukan pada {top['title']} {top['pasal']}. "
            f"Intinya, {top['snippet']}"
        )

    def answer(self, query: str) -> Dict[str, Any]:
        query_type = classify_regulation_query(query)
        topics = detect_topics(query)
        results = self.search(query, top_k=5)

        if not results:
            return {
                "question": query,
                "query_type": query_type,
                "topics": topics,
                "answer": "Saya belum menemukan pasal yang cukup relevan dari basis regulasi yang tersedia.",
                "sources": [],
                "results": [],
            }

        if query_type == "definition_query":
            answer = self._answer_definition(query, results)
        elif query_type in {"zoning_query", "route_query", "wppnri_query", "zoning_aceh_query"}:
            answer = self._answer_zoning(query, results, topics)
        elif query_type == "distance_query":
            answer = self._answer_distance(query, results)
        elif query_type in {"permission_query", "requirement_query", "obligation_query", "placement_query", "location_query"}:
            answer = self._answer_permission(query, results)
        elif query_type in {"prohibition_query", "forbidden_gear_query"}:
            answer = self._answer_prohibition(query, results)
        elif query_type == "license_query":
            answer = self._answer_license(query, results)
        elif query_type in {"gear_query", "allowed_gear_query", "list_query"}:
            answer = self._answer_gear_list(query, results)
        elif query_type == "count_query":
            answer = self._answer_count(query, results)
        elif query_type in {"authority_query", "sanction_query"}:
            answer = self._answer_authority(query, results)
        elif query_type == "institution_query":
            answer = self._answer_institution(query, results)
        else:
            answer = self._answer_general(query, results)

        sources = [
            {
                "title": r["title"],
                "pasal": r["pasal"],
                "score": r["score"],
            }
            for r in results[:3]
        ]

        return {
            "question": query,
            "query_type": query_type,
            "topics": topics,
            "answer": answer,
            "sources": sources,
            "results": results,
        }