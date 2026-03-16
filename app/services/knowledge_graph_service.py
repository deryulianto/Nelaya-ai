from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List, Optional


GRAPH_DIR = Path("data/knowledge_graph")
NODES_PATH = GRAPH_DIR / "nodes.json"
EDGES_PATH = GRAPH_DIR / "edges.json"
ACEH_MARINE_MAP_PATH = GRAPH_DIR / "aceh_marine_mapping.json"


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


class KnowledgeGraphService:
    def __init__(self) -> None:
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self._node_map: Dict[str, Dict[str, Any]] = {}
        self.aceh_marine_map: Dict[str, List[str]] = {}
        self.load()

    def load(self) -> None:
        self.nodes = []
        self.edges = []
        self._node_map = {}
        self.aceh_marine_map = {}

        if NODES_PATH.exists():
            try:
                self.nodes = json.loads(NODES_PATH.read_text(encoding="utf-8"))
            except Exception:
                self.nodes = []

        if EDGES_PATH.exists():
            try:
                self.edges = json.loads(EDGES_PATH.read_text(encoding="utf-8"))
            except Exception:
                self.edges = []

        if ACEH_MARINE_MAP_PATH.exists():
            try:
                self.aceh_marine_map = json.loads(ACEH_MARINE_MAP_PATH.read_text(encoding="utf-8"))
            except Exception:
                self.aceh_marine_map = {}

        for node in self.nodes:
            node_id = str(node.get("id", "")).strip()
            if node_id:
                self._node_map[node_id] = node

    def stats(self) -> Dict[str, int]:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
        }

    def find_relations(entity_id):
        return [r for r in relations if r["source"] == entity_id]

    def find_reverse(entity_id):
        return [r for r in relations if r["target"] == entity_id]


    def find_node(self, query: str) -> Optional[Dict[str, Any]]:
        q = _norm(query)

        for node in self.nodes:
            if _norm(node.get("name", "")) == q:
                return node

        for node in self.nodes:
            aliases = node.get("aliases", []) or []
            for alias in aliases:
                if _norm(alias) == q:
                    return node

        for node in self.nodes:
            if q in _norm(node.get("name", "")):
                return node

        for node in self.nodes:
            aliases = node.get("aliases", []) or []
            for alias in aliases:
                if q in _norm(alias):
                    return node

        for node in self.nodes:
            if _norm(node.get("name", "")) in q:
                return node
            aliases = node.get("aliases", []) or []
            for alias in aliases:
                if _norm(alias) in q:
                    return node

        return None

    def neighbors(self, node_id: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        for edge in self.edges:
            if edge.get("source") == node_id:
                target_id = edge.get("target")
                out.append({
                    "direction": "out",
                    "relation": edge.get("relation"),
                    "node": self._node_map.get(target_id, {"id": target_id}),
                })
            elif edge.get("target") == node_id:
                source_id = edge.get("source")
                out.append({
                    "direction": "in",
                    "relation": edge.get("relation"),
                    "node": self._node_map.get(source_id, {"id": source_id}),
                })

        return out

    def _marine_mapping_answer(self, question: str) -> Optional[Dict[str, Any]]:
        q = _norm(question)

        # count WPPNRI in Aceh
        if "wppnri" in q and ("ada berapa" in q or "berapa" in q or "jumlah" in q):
            for region_name, ids in self.aceh_marine_map.items():
                if region_name in q:
                    names = [
                        self._node_map.get(x, {}).get("name", x).replace("WPPNRI ", "")
                        for x in ids
                    ]
                    readable = [f"WPPNRI {n}" for n in names]
                    return {
                        "headline": f"Ada {len(ids)} WPPNRI yang paling relevan untuk {region_name.title()}.",
                        "summary": (
                            f"Dalam pembacaan awal NELAYA-AI, wilayah {region_name.title()} terutama terkait dengan "
                            f"{len(ids)} WPPNRI, yaitu {', '.join(readable)}."
                        ),
                        "node": {
                            "id": region_name.replace(" ", "_"),
                            "name": region_name.title(),
                            "type": "marine_region_mapping",
                            "summary": f"Mapping wilayah laut untuk {region_name.title()}."
                        },
                        "relations": [f"{region_name.title()} — terkait_dengan — {x}" for x in readable],
                        "sources": [
                            {
                                "title": self._node_map.get(x, {}).get("name", x),
                                "pasal": "Knowledge Graph",
                                "score": 100,
                            }
                            for x in ids
                        ][:3],
                        "stats": self.stats(),
                        "query_type": "graph_count_query",
                        "topics": ["wppnri", region_name],
                    }

        return None

    def answer(self, question: str) -> Optional[Dict[str, Any]]:
        q = _norm(question)

        # 1. hard-route curated marine mapping first
        mapped = self._marine_mapping_answer(question)
        if mapped:
            return mapped

        priority_terms = [
            "panglima laot lhok",
            "panglima laot",
            "masyarakat hukum adat laut",
            "selat malaka",
            "laut andaman",
            "samudera hindia",
            "wppnri 571",
            "wppnri 572",
            "rumpon",
            "alat tangkap",
            "zona perikanan tangkap",
            "kawasan konservasi",
            "nelayan kecil",
        ]

        node = None
        for term in priority_terms:
            if term in q:
                node = self.find_node(term)
                if node:
                    break

        if node is None:
            node = self.find_node(question)

        if node is None:
            return None

        near = self.neighbors(str(node["id"]))

        sources: List[Dict[str, Any]] = []
        bullets: List[str] = []

        for item in near[:6]:
            rel = str(item.get("relation", "")).replace("_", " ")
            n = item.get("node", {})
            n_name = n.get("name", n.get("id", "node"))
            bullets.append(f"{node['name']} — {rel} — {n_name}")

            if n.get("type") == "regulation":
                sources.append({
                    "title": n.get("name"),
                    "pasal": "Knowledge Graph",
                    "score": 100,
                })

        if "apa itu panglima laot" in q or "apa fungsi panglima laot" in q or "panglima laot" in q:
            summary = (
                "Panglima Laot adalah lembaga adat laut Aceh yang memimpin dan mengatur adat-istiadat "
                "di bidang pesisir dan kelautan. Dalam knowledge graph NELAYA-AI, Panglima Laot "
                "terhubung dengan Masyarakat Hukum Adat Laut dan diakui dalam Qanun Aceh No. 1 Tahun 2020."
            )
            query_type = "institution_graph_query"
            topics = ["panglima_laot", "adat_laut", "aceh"]

        elif "selat malaka" in q and "wppnri" in q:
            summary = (
                "Selat Malaka dalam knowledge graph NELAYA-AI terhubung dengan WPPNRI 571."
            )
            query_type = "marine_relation_query"
            topics = ["selat_malaka", "wppnri_571"]

        elif "rumpon" in q:
            summary = (
                "Rumpon dalam knowledge graph NELAYA-AI terhubung dengan Permen KP No. 36 Tahun 2023 "
                "dan memiliki relasi larangan penempatan di kawasan konservasi."
            )
            query_type = "marine_relation_query"
            topics = ["rumpon", "kawasan_konservasi"]

        else:
            summary = (
                f"{node['name']} ditemukan dalam knowledge graph NELAYA-AI dan memiliki beberapa relasi penting "
                "dengan entitas laut, regulasi, atau kelembagaan terkait."
            )
            query_type = "knowledge_graph_query"
            topics = [str(node.get("id"))]

        return {
            "headline": f"Relasi pengetahuan ditemukan untuk {node['name']}.",
            "summary": summary,
            "node": {
                "id": node.get("id"),
                "name": node.get("name"),
                "type": node.get("type"),
                "summary": node.get("summary"),
            },
            "relations": bullets,
            "sources": sources[:3],
            "stats": self.stats(),
            "query_type": query_type,
            "topics": topics,
        }
