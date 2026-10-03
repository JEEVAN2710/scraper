"""Knowledge Graph Engine and Graphifier.

Transforms relational database entities, financial reports, risk disclosures,
and quarterly concall chunks into an in-memory, persistent Knowledge Graph
with semantic triples and direct neighborhood traversal (eliminating SQL search queries).
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.settings import Settings, get_settings
from app.database.connection import DatabaseManager, get_db_manager

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_PATH = Path("data/knowledge_graph.json")


class KnowledgeGraph:
    """In-memory Knowledge Graph index with fast node-and-edge traversal and JSON serialization."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or DEFAULT_GRAPH_PATH
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []

        # Adjacency indices for O(1) traversal
        self._adj_out: Dict[str, List[Dict[str, Any]]] = {}
        self._adj_in: Dict[str, List[Dict[str, Any]]] = {}

        # Inverted indices for instant entry-point lookup
        self._ticker_index: Dict[str, str] = {}
        self._name_index: Dict[str, str] = {}
        self._type_index: Dict[str, Set[str]] = {}

    def clear(self) -> None:
        """Reset the graph."""
        self.nodes.clear()
        self.edges.clear()
        self._adj_out.clear()
        self._adj_in.clear()
        self._ticker_index.clear()
        self._name_index.clear()
        self._type_index.clear()

    def add_node(
        self,
        node_id: str,
        label: str,
        node_type: str,
        properties: Optional[Dict[str, Any]] = None,
        color: Optional[str] = None,
        size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Add or update a node in the graph."""
        props = properties or {}
        node = {
            "id": node_id,
            "label": label,
            "type": node_type,
            "properties": props,
            "color": color or self._default_color(node_type),
            "size": size or self._default_size(node_type),
        }
        self.nodes[node_id] = node

        # Update type index
        self._type_index.setdefault(node_type, set()).add(node_id)

        # Index company nodes by ticker and normalized name
        if node_type == "company":
            ticker = str(props.get("ticker") or label).strip().upper()
            if ticker:
                self._ticker_index[ticker] = node_id
            name = str(props.get("name") or label).strip().lower()
            if name:
                self._name_index[name] = node_id

        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Add a directed edge between two existing nodes."""
        if source_id not in self.nodes or target_id not in self.nodes:
            logger.debug(
                "Skipping edge %s -> %s: one or both nodes missing", source_id, target_id
            )
            return None

        edge_id = f"{source_id}_{relation_type}_{target_id}"
        # Check duplicate
        for existing in self._adj_out.get(source_id, []):
            if existing["id"] == edge_id:
                return existing

        edge = {
            "id": edge_id,
            "source": source_id,
            "target": target_id,
            "label": relation_type,
            "properties": properties or {},
        }
        self.edges.append(edge)

        self._adj_out.setdefault(source_id, []).append(edge)
        self._adj_in.setdefault(target_id, []).append(edge)
        return edge

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Fetch node by ID."""
        return self.nodes.get(node_id)

    def get_outgoing_edges(
        self, node_id: str, relation_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return all outgoing edges from a node, optionally filtered by relationship type."""
        edges = self._adj_out.get(node_id, [])
        if relation_type:
            return [e for e in edges if e["label"] == relation_type]
        return edges

    def get_connected_nodes(
        self, node_id: str, relation_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve target nodes connected to this node via outgoing edges."""
        edges = self.get_outgoing_edges(node_id, relation_type)
        targets = []
        for edge in edges:
            target_node = self.nodes.get(edge["target"])
            if target_node:
                targets.append(target_node)
        return targets

    def find_company_node(self, query: str) -> Optional[Dict[str, Any]]:
        """Instant O(1) lookup of a company node by ticker, ID, or substring."""
        q_upper = query.strip().upper()
        if q_upper in self._ticker_index:
            return self.nodes.get(self._ticker_index[q_upper])

        # By direct node ID
        if query in self.nodes and self.nodes[query]["type"] == "company":
            return self.nodes[query]

        comp_id = f"comp_{query}"
        if comp_id in self.nodes:
            return self.nodes[comp_id]

        q_lower = query.strip().lower()
        if q_lower in self._name_index:
            return self.nodes.get(self._name_index[q_lower])

        # Substring match on company names
        for name, n_id in self._name_index.items():
            if q_lower in name or name in q_lower:
                return self.nodes.get(n_id)

        return None

    def get_company_subgraph(self, company_node_id: str) -> Dict[str, Any]:
        """Extract the full connected 1-hop and 2-hop neighborhood for a company.

        Returns all financial metrics, risk factors, filings, concall guidance,
        and evidence links without running any SQL search query.
        """
        if company_node_id not in self.nodes:
            return {"nodes": [], "edges": []}

        sub_node_ids: Set[str] = {company_node_id}
        sub_edges: List[Dict[str, Any]] = []

        # 1-hop traversal: Outgoing edges from company
        for edge in self._adj_out.get(company_node_id, []):
            sub_edges.append(edge)
            sub_node_ids.add(edge["target"])

        # 2-hop traversal: Connections between documents and metrics/risks/guidance
        for n_id in list(sub_node_ids):
            for edge in self._adj_out.get(n_id, []):
                if edge["target"] in sub_node_ids:
                    if edge not in sub_edges:
                        sub_edges.append(edge)

        sub_nodes = [self.nodes[n_id] for n_id in sub_node_ids if n_id in self.nodes]
        return {
            "nodes": sub_nodes,
            "edges": sub_edges,
            "company": self.nodes[company_node_id],
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete graph structure to a JSON-ready dictionary."""
        return {
            "version": "2.0",
            "updated_at": datetime.now().isoformat(),
            "summary": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "companies": len(self._type_index.get("company", set())),
                "metrics": len(self._type_index.get("metric", set())),
                "risks": len(self._type_index.get("risk", set())),
                "documents": len(self._type_index.get("document", set())),
                "guidance": len(self._type_index.get("guidance", set())),
            },
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        }

    def save_to_disk(self, target_path: Optional[Path] = None) -> Path:
        """Persist the Knowledge Graph to disk as JSON."""
        out_path = target_path or self.storage_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(
            "Saved Knowledge Graph with %d nodes and %d edges to %s",
            len(self.nodes),
            len(self.edges),
            out_path,
        )
        return out_path

    def load_from_disk(self, target_path: Optional[Path] = None) -> bool:
        """Load graph nodes and edges from JSON storage into memory."""
        in_path = target_path or self.storage_path
        if not in_path.exists():
            logger.info("Knowledge Graph storage file not found at %s", in_path)
            return False

        try:
            with open(in_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.clear()
            for node in data.get("nodes", []):
                self.add_node(
                    node_id=node["id"],
                    label=node["label"],
                    node_type=node["type"],
                    properties=node.get("properties"),
                    color=node.get("color"),
                    size=node.get("size"),
                )

            for edge in data.get("edges", []):
                self.add_edge(
                    source_id=edge["source"],
                    target_id=edge["target"],
                    relation_type=edge["label"],
                    properties=edge.get("properties"),
                )

            logger.info(
                "Successfully loaded Knowledge Graph from %s (%d nodes, %d edges)",
                in_path,
                len(self.nodes),
                len(self.edges),
            )
            return True
        except Exception as exc:
            logger.exception("Failed to load Knowledge Graph from %s: %s", in_path, exc)
            return False

    @staticmethod
    def _default_color(node_type: str) -> str:
        colors = {
            "company": "#f59e0b",      # Amber
            "metric": "#10b981",       # Emerald
            "risk": "#f43f5e",         # Rose
            "document": "#06b6d4",     # Cyan
            "guidance": "#a855f7",     # Purple
            "segment": "#3b82f6",      # Blue
        }
        return colors.get(node_type, "#94a3b8")

    @staticmethod
    def _default_size(node_type: str) -> int:
        sizes = {
            "company": 28,
            "document": 22,
            "metric": 18,
            "guidance": 18,
            "risk": 17,
            "segment": 16,
        }
        return sizes.get(node_type, 16)


class Graphifier:
    """Transforms relational database records, filings, and concall transcripts

    into an interconnected Knowledge Graph with pre-extracted semantic guidance.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        graph: Optional[KnowledgeGraph] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.graph = graph or KnowledgeGraph(self.settings.PROCESSED_DIR / "knowledge_graph.json")

    def graphify_from_db(self) -> KnowledgeGraph:
        """Read all companies, documents, metrics, risks, and concall chunks from MySQL

        and build the complete persistent knowledge graph.
        """
        logger.info("=== Starting Database Graphification ===")
        self.graph.clear()

        try:
            with self.db.get_cursor() as (cursor, _):
                # 1. Fetch Companies
                cursor.execute("SELECT * FROM companies ORDER BY id ASC;")
                companies = cursor.fetchall()
                logger.info("Graphifying %d companies...", len(companies))

                for comp in companies:
                    cid = comp["id"]
                    ticker = (comp.get("ticker") or comp["name"][:6]).strip().upper()
                    comp_node_id = f"comp_{cid}"

                    comp_ratios = {}
                    if comp.get("ratios_json"):
                        try:
                            comp_ratios = json.loads(comp["ratios_json"]) if isinstance(comp["ratios_json"], str) else comp["ratios_json"]
                        except Exception:
                            comp_ratios = {}

                    self.graph.add_node(
                        node_id=comp_node_id,
                        label=ticker,
                        node_type="company",
                        properties={
                            "company_id": cid,
                            "name": comp["name"],
                            "ticker": ticker,
                            "website": comp.get("website", ""),
                            "about": comp.get("about", ""),
                            "sector": comp.get("sector", ""),
                            "ratios": comp_ratios,
                        },
                        color="#f59e0b",
                        size=28,
                    )

                # 2. Fetch Documents
                cursor.execute("SELECT * FROM documents ORDER BY id ASC;")
                documents = cursor.fetchall()
                logger.info("Graphifying %d documents...", len(documents))

                for doc in documents:
                    did = doc["id"]
                    cid = doc["company_id"]
                    comp_node_id = f"comp_{cid}"
                    doc_node_id = f"doc_{did}"

                    dtype = doc.get("document_type", "annual_report")
                    is_concall = dtype == "concall_transcript" or "concall" in str(doc.get("file_name", "")).lower()
                    doc_color = "#a855f7" if is_concall else "#06b6d4"
                    period = doc.get("report_period") or "Latest"
                    label = f"Concall {period}" if is_concall else f"Report {period}"

                    self.graph.add_node(
                        node_id=doc_node_id,
                        label=label,
                        node_type="document",
                        properties={
                            "document_id": did,
                            "company_id": cid,
                            "file_name": doc["file_name"],
                            "document_type": dtype,
                            "period": period,
                            "file_hash": doc.get("file_hash", ""),
                            "status": doc.get("processing_status", "processed"),
                        },
                        color=doc_color,
                        size=22,
                    )

                    # Edge: Company -> Document
                    rel = "CONCALL_FILED" if is_concall else "ANNUAL_FILING"
                    self.graph.add_edge(comp_node_id, doc_node_id, rel, {"period": period})

                # 3. Fetch Financial Data
                cursor.execute("SELECT * FROM financial_data ORDER BY company_id, period ASC;")
                financial_rows = cursor.fetchall()
                logger.info("Graphifying %d financial metrics...", len(financial_rows))

                for fin in financial_rows:
                    fid = fin["id"]
                    cid = fin["company_id"]
                    did = fin.get("document_id")
                    period = fin.get("period", "Latest")
                    comp_node_id = f"comp_{cid}"
                    fin_node_id = f"fin_{fid}"

                    curr = fin.get("currency", "USD")
                    sym = "₹" if curr == "INR" else "$"
                    divider = 1e7 if curr == "INR" else 1e9
                    unit = "Cr" if curr == "INR" else "B"

                    rev = float(fin["revenue"]) if fin.get("revenue") is not None else None
                    rev_str = f"{sym}{rev/divider:.1f}{unit}" if rev is not None else "N/A"
                    growth = float(fin["revenue_growth"]) if fin.get("revenue_growth") is not None else None
                    profit = float(fin["net_profit"]) if fin.get("net_profit") is not None else None
                    margin = float(fin["operating_margin"]) if fin.get("operating_margin") is not None else None
                    eps = float(fin["eps"]) if fin.get("eps") is not None else None

                    self.graph.add_node(
                        node_id=fin_node_id,
                        label=f"{period}: {rev_str}",
                        node_type="metric",
                        properties={
                            "metric_id": fid,
                            "company_id": cid,
                            "period": period,
                            "revenue": rev,
                            "revenue_formatted": rev_str,
                            "revenue_growth": growth,
                            "revenue_growth_pct": f"{growth*100:+.1f}%" if growth is not None else "N/A",
                            "net_profit": profit,
                            "operating_margin": margin,
                            "operating_margin_pct": f"{margin*100:.1f}%" if margin is not None else "N/A",
                            "eps": eps,
                            "currency": curr,
                        },
                        color="#10b981",
                        size=18,
                    )

                    # Edge: Company -> Metric
                    self.graph.add_edge(
                        comp_node_id,
                        fin_node_id,
                        "REPORTED_FINANCIALS",
                        {"period": period, "revenue": rev_str},
                    )

                    # Edge: Document -> Metric (evidence)
                    if did:
                        doc_node_id = f"doc_{did}"
                        self.graph.add_edge(doc_node_id, fin_node_id, "EVIDENCES")

                # 4. Fetch Risk Factors
                cursor.execute(
                    "SELECT r.*, d.file_name as doc_file FROM risk_factors r "
                    "LEFT JOIN documents d ON r.document_id = d.id "
                    "ORDER BY r.page_number ASC;"
                )
                risks = cursor.fetchall()
                logger.info("Graphifying %d risk disclosures...", len(risks))

                for r in risks:
                    rid = r["id"]
                    cid = r["company_id"]
                    did = r.get("document_id")
                    risk_title = r.get("risk", "Risk Factor")
                    page = r.get("page_number", 1)
                    comp_node_id = f"comp_{cid}"
                    risk_node_id = f"risk_{rid}"

                    short_label = (risk_title[:16] + "..") if len(risk_title) > 16 else risk_title
                    self.graph.add_node(
                        node_id=risk_node_id,
                        label=f"⚠️ {short_label} (p.{page})",
                        node_type="risk",
                        properties={
                            "risk_id": rid,
                            "company_id": cid,
                            "category": risk_title,
                            "description": r.get("description", ""),
                            "page_number": page,
                            "source_doc": r.get("doc_file", "Filing.pdf"),
                        },
                        color="#f43f5e",
                        size=17,
                    )

                    # Edge: Company -> Risk
                    self.graph.add_edge(
                        comp_node_id,
                        risk_node_id,
                        "HAS_RISK",
                        {"category": risk_title, "page": page},
                    )

                    # Edge: Document -> Risk (provenance)
                    if did:
                        doc_node_id = f"doc_{did}"
                        self.graph.add_edge(doc_node_id, risk_node_id, f"CITES_P{page}")

                # 5. Extract and Graphify Semantic Guidance & Commentary from Concall Chunks
                cursor.execute(
                    "SELECT c.id, c.document_id, c.chunk_index, c.page_start, c.page_end, c.content, "
                    "d.file_name, d.report_period, d.company_id, comp.ticker "
                    "FROM document_chunks c "
                    "JOIN documents d ON c.document_id = d.id "
                    "JOIN companies comp ON d.company_id = comp.id "
                    "WHERE d.document_type = 'concall_transcript' "
                    "ORDER BY d.id DESC, c.chunk_index ASC;"
                )
                concall_chunks = cursor.fetchall()
                logger.info(
                    "Analyzing %d concall chunks for semantic guidance and management commentary...",
                    len(concall_chunks),
                )

                extracted_guidance = self.extract_semantic_guidance(concall_chunks)
                logger.info("Graphifying %d extracted guidance items...", len(extracted_guidance))

                for item in extracted_guidance:
                    gid = item["id"]
                    cid = item["company_id"]
                    did = item["document_id"]
                    comp_node_id = f"comp_{cid}"
                    guidance_node_id = f"guidance_{gid}"

                    self.graph.add_node(
                        node_id=guidance_node_id,
                        label=f"💡 {item['category']} ({item['period']})",
                        node_type="guidance",
                        properties={
                            "category": item["category"],
                            "period": item["period"],
                            "statement": item["statement"],
                            "source_doc": item["source_doc"],
                            "page": item["page"],
                        },
                        color="#a855f7",
                        size=18,
                    )

                    # Edge: Company -> Guidance
                    self.graph.add_edge(
                        comp_node_id,
                        guidance_node_id,
                        "MENTIONS_GUIDANCE",
                        {"category": item["category"], "period": item["period"]},
                    )

                    # Edge: Document -> Guidance
                    if did:
                        doc_node_id = f"doc_{did}"
                        self.graph.add_edge(
                            doc_node_id,
                            guidance_node_id,
                            f"CITES_{item['page']}",
                        )

            # Also incorporate demo companies if not already present in the graph
            self._incorporate_demo_data()

            # Persist to disk
            self.graph.save_to_disk()
            logger.info("=== Database Graphification Completed Successfully ===")
            return self.graph

        except Exception as exc:
            logger.exception("Failed during database graphification: %s", exc)
            raise

    def add_company_data(self, company_data: Dict[str, Any]) -> None:
        """Incrementally add or update a company, its documents, metrics, and risks in the graph."""
        cid = company_data.get("id") or company_data.get("company_id", 999)
        ticker = (company_data.get("ticker") or company_data["name"][:6]).strip().upper()
        comp_node_id = f"comp_{cid}"

        # 1. Company Node
        self.graph.add_node(
            node_id=comp_node_id,
            label=ticker,
            node_type="company",
            properties={
                "company_id": cid,
                "name": company_data["name"],
                "ticker": ticker,
                "website": company_data.get("website", ""),
            },
            color="#f59e0b",
            size=28,
        )

        # 2. Documents
        for doc in company_data.get("documents", []):
            did = doc.get("id", f"{cid}_{doc.get('file_name', 'doc')}")
            doc_node_id = f"doc_{did}"
            dtype = doc.get("document_type", "annual_report")
            is_concall = dtype == "concall_transcript" or "concall" in str(doc.get("file_name", "")).lower()
            doc_color = "#a855f7" if is_concall else "#06b6d4"
            period = doc.get("report_period") or "Latest"

            self.graph.add_node(
                node_id=doc_node_id,
                label=f"Concall {period}" if is_concall else f"Report {period}",
                node_type="document",
                properties={
                    "document_id": did,
                    "company_id": cid,
                    "file_name": doc.get("file_name", "report.pdf"),
                    "document_type": dtype,
                    "period": period,
                    "file_hash": doc.get("file_hash", ""),
                    "status": doc.get("processing_status", "processed"),
                },
                color=doc_color,
                size=22,
            )
            rel = "CONCALL_FILED" if is_concall else "ANNUAL_FILING"
            self.graph.add_edge(comp_node_id, doc_node_id, rel, {"period": period})

        # 3. Financial Data
        for fin in company_data.get("financial_data", []):
            period = fin.get("period", "Latest")
            fid = fin.get("id", f"{cid}_{period}")
            fin_node_id = f"fin_{fid}"
            curr = fin.get("currency", "USD")
            sym = "₹" if curr == "INR" else "$"
            divider = 1e7 if curr == "INR" else 1e9
            unit = "Cr" if curr == "INR" else "B"

            rev = float(fin["revenue"]) if fin.get("revenue") is not None else None
            rev_str = f"{sym}{rev/divider:.1f}{unit}" if rev is not None else "N/A"
            growth = float(fin["revenue_growth"]) if fin.get("revenue_growth") is not None else None
            profit = float(fin["net_profit"]) if fin.get("net_profit") is not None else None
            margin = float(fin["operating_margin"]) if fin.get("operating_margin") is not None else None
            eps = float(fin["eps"]) if fin.get("eps") is not None else None

            self.graph.add_node(
                node_id=fin_node_id,
                label=f"{period}: {rev_str}",
                node_type="metric",
                properties={
                    "metric_id": fid,
                    "company_id": cid,
                    "period": period,
                    "revenue": rev,
                    "revenue_formatted": rev_str,
                    "revenue_growth": growth,
                    "revenue_growth_pct": f"{growth*100:+.1f}%" if growth is not None else "N/A",
                    "net_profit": profit,
                    "operating_margin": margin,
                    "operating_margin_pct": f"{margin*100:.1f}%" if margin is not None else "N/A",
                    "eps": eps,
                    "currency": curr,
                },
                color="#10b981",
                size=18,
            )
            self.graph.add_edge(comp_node_id, fin_node_id, "REPORTED_FINANCIALS", {"period": period})

        # 4. Risks
        for r in company_data.get("risks", []):
            risk_title = r.get("risk", "Risk Factor")
            rid = r.get("id", f"{cid}_{risk_title[:6]}")
            risk_node_id = f"risk_{rid}"
            page = r.get("page_number", 1)
            short_label = (risk_title[:16] + "..") if len(risk_title) > 16 else risk_title

            self.graph.add_node(
                node_id=risk_node_id,
                label=f"⚠️ {short_label} (p.{page})",
                node_type="risk",
                properties={
                    "risk_id": rid,
                    "company_id": cid,
                    "category": risk_title,
                    "description": r.get("description", ""),
                    "page_number": page,
                    "source_doc": r.get("source_doc", "Filing.pdf"),
                },
                color="#f43f5e",
                size=17,
            )
            self.graph.add_edge(comp_node_id, risk_node_id, "HAS_RISK", {"category": risk_title, "page": page})

        self.graph.save_to_disk()

    def _incorporate_demo_data(self) -> None:
        """Incorporate standard baseline demo companies if not already present."""
        try:
            from app.api.routes import DEMO_COMPANIES
            for demo in DEMO_COMPANIES:
                ticker = demo.get("ticker", "").upper()
                if not self.graph.find_company_node(ticker):
                    logger.info("Adding baseline demo company '%s' to Knowledge Graph...", ticker)
                    self.add_company_data(demo)
        except Exception as exc:
            logger.debug("Demo data incorporation note: %s", exc)

    def extract_semantic_guidance(
        self, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Identify strategic guidance, capital expenditure, and forward-looking statements

        from concall transcript chunks using domain financial heuristics.
        """
        guidance_items: List[Dict[str, Any]] = []
        guidance_categories = [
            (
                "CapEx & Capital Allocation",
                r"(capex|capital\s+expenditure|investment\s+of|outlay|investing\s+around|spend\s+around)",
            ),
            (
                "Revenue & Margin Guidance",
                r"(growth\s+guidance|margin\s+target|expect\s+to\s+grow|target\s+of|guidance\s+for|revenue\s+target)",
            ),
            (
                "Capacity & Project Commissioning",
                r"(commissioning|operationalize|expansion\s+phase|new\s+facility|pipeline|commercial\s+operation)",
            ),
            (
                "Debt & Liquidity Strategy",
                r"(debt\s+reduction|leverage|cash\s+flow|liquidity|refinanc|borrowing)",
            ),
            (
                "Strategic Order Book & Clients",
                r"(order\s+book|deal\s+win|new\s+client|contract\s+value|backlog)",
            ),
        ]

        seen_statements: Set[str] = set()

        for chunk in chunks:
            content = chunk.get("content", "")
            if len(content) < 80:
                continue

            # Split into individual sentences
            sentences = re.split(r"(?<=[.!?])\s+", content)
            p_start = chunk.get("page_start", 1)
            p_end = chunk.get("page_end", 1)
            page_str = f"Page {p_start}" if p_start == p_end else f"Pages {p_start}-{p_end}"

            for sentence in sentences:
                s_clean = sentence.strip()
                if len(s_clean) < 50 or len(s_clean) > 400:
                    continue

                for cat_title, pattern in guidance_categories:
                    if re.search(pattern, s_clean, re.IGNORECASE):
                        # Avoid duplicates
                        s_key = s_clean[:60].lower()
                        if s_key in seen_statements:
                            continue
                        seen_statements.add(s_key)

                        guidance_items.append({
                            "id": f"{chunk.get('id', 0)}_{len(guidance_items)}",
                            "company_id": chunk["company_id"],
                            "document_id": chunk.get("document_id"),
                            "ticker": chunk.get("ticker", ""),
                            "category": cat_title,
                            "period": chunk.get("report_period", "Latest"),
                            "statement": s_clean,
                            "source_doc": chunk.get("file_name", "Concall.pdf"),
                            "page": page_str,
                        })
                        break

                if len(guidance_items) >= 60:
                    break

            if len(guidance_items) >= 60:
                break

        return guidance_items


# Global singleton instance helper
_global_graph: Optional[KnowledgeGraph] = None


def get_knowledge_graph(settings: Optional[Settings] = None) -> KnowledgeGraph:
    """Return the shared in-memory KnowledgeGraph instance, auto-loading from disk if available."""
    global _global_graph
    if _global_graph is None:
        cfg = settings or get_settings()
        storage = cfg.PROCESSED_DIR / "knowledge_graph.json"
        _global_graph = KnowledgeGraph(storage)
        if not _global_graph.load_from_disk():
            # If not yet persisted, attempt graphifying from database
            try:
                db_mgr = get_db_manager(cfg)
                graphifier = Graphifier(db_mgr, _global_graph, cfg)
                graphifier.graphify_from_db()
            except Exception as exc:
                logger.warning("Could not auto-graphify database at initialization: %s", exc)
    return _global_graph
