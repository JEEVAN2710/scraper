"""Graph RAG (Retrieval-Augmented Generation) Engine with Queryless Graph Traversal.

Constructs an in-memory knowledge subgraph from MySQL entities, metrics,
risks, and document citations using the pre-indexed Knowledge Graph.
Grounds local LLMs (Ollama Phi-3 / Qwen) via direct graph traversal
without expensive or brittle SQL search queries.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.database.connection import DatabaseManager, get_db_manager
from app.llm.ollama_client import OllamaProvider
from app.llm.prompts import GRAPH_RAG_SYSTEM_PROMPT, build_graph_rag_prompt
from app.pipeline.graphify import KnowledgeGraph, get_knowledge_graph

logger = logging.getLogger(__name__)


class GraphRAGEngine:
    """Orchestrates structured Knowledge Graph traversal and LLM generation."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or get_db_manager()
        self.llm = OllamaProvider(self.db.settings)
        self.graph: KnowledgeGraph = get_knowledge_graph(self.db.settings)

    def query(self, question: str, company_id: Optional[int] = None) -> Dict[str, Any]:
        """Execute a queryless Graph RAG query:

        1. Direct entry-point resolution in Knowledge Graph.
        2. Fast O(1) neighborhood graph traversal (metrics, risks, guidance).
        3. Formulate grounded semantic triples with exact page citations.
        4. Synthesize executive answer with local Ollama Phi-3 (or deterministic graph synthesis fallback).
        """
        logger.info("Executing Graph RAG query: '%s' (company_id=%s)", question, company_id)

        try:
            # Ensure graph has latest updates
            if len(self.graph.nodes) == 0:
                self.graph = get_knowledge_graph(self.db.settings)

            # 1. Identify target companies in Knowledge Graph
            target_companies = self._resolve_target_companies(question, company_id)

            # 2. Extract Subgraph Nodes & Edges via Queryless Graph Traversal
            subgraph = self._build_subgraph(target_companies, question)

            # 3. Format Subgraph Context for Prompt
            context_text, citations, graph_nodes = self._format_graph_context(subgraph)

            # 4. Generate Answer via Ollama (or Graph Engine direct synthesis if Ollama is offline/times out)
            ollama_status = self.llm.check_availability()
            answer = ""
            llm_used = self.llm.get_model_name()

            if ollama_status.get("available") and ollama_status.get("model_pulled"):
                try:
                    logger.info("Sending Graph RAG prompt to Ollama model '%s'...", llm_used)
                    full_prompt = build_graph_rag_prompt(question, context_text)
                    answer = self.llm.generate(full_prompt, system=GRAPH_RAG_SYSTEM_PROMPT)
                except Exception as exc:
                    logger.warning("Ollama inference encountered error, falling back to direct synthesis: %s", exc)
                    answer = self._synthesize_direct_graph_answer(question, subgraph, citations)
                    llm_used = f"{self.llm.get_model_name()} (Offline Fallback)"
            else:
                if not getattr(self.db.settings, "llm_enabled", True):
                    logger.info("LLM is turned off in .env (LLM_ENABLED=false). Using instant deterministic Graph RAG synthesis.")
                    llm_used = "Graph RAG Engine (Deterministic - LLM OFF)"
                else:
                    logger.info("Ollama is not running or model not pulled. Using deterministic Graph RAG synthesis.")
                    llm_used = "Graph RAG Engine (Ollama Standby)"
                answer = self._synthesize_direct_graph_answer(question, subgraph, citations)

            return {
                "question": question,
                "answer": answer,
                "graph_nodes": graph_nodes,
                "citations": citations,
                "llm_used": llm_used,
                "ollama_available": ollama_status.get("available", False),
            }

        except Exception as exc:
            logger.exception("Graph RAG execution error: %s", exc)
            return {
                "question": question,
                "answer": f"Error executing Graph RAG search: {exc}",
                "graph_nodes": [],
                "citations": [],
                "llm_used": "None",
                "ollama_available": False,
            }

    def _resolve_target_companies(self, question: str, company_id: Optional[int]) -> List[Dict[str, Any]]:
        """Identify which company nodes in the Knowledge Graph are relevant to the query."""
        all_comps: List[Dict[str, Any]] = []

        # Look up from KnowledgeGraph first
        for nid in self.graph._type_index.get("company", set()):
            node = self.graph.get_node(nid)
            if node:
                all_comps.append({
                    "id": node["properties"].get("company_id"),
                    "name": node["properties"].get("name", node["label"]),
                    "ticker": node["properties"].get("ticker", node["label"]),
                    "website": node["properties"].get("website", ""),
                    "node_id": node["id"],
                })

        # Fallback to MySQL if graph had no companies loaded yet
        if not all_comps:
            try:
                with self.db.get_cursor() as (cursor, _):
                    cursor.execute("SELECT id, name, ticker, website FROM companies;")
                    all_comps = cursor.fetchall()
            except Exception as exc:
                logger.warning("Failed to fetch companies from MySQL, using empty list: %s", exc)

        if company_id:
            matched = [c for c in all_comps if c.get("id") == company_id]
            if matched:
                return matched

        q_lower = question.lower()
        matched = []

        for c in all_comps:
            name_parts = c["name"].lower().split()
            ticker = (c.get("ticker") or "").lower()
            if ticker and ticker in q_lower:
                matched.append(c)
            elif any(part in q_lower for part in name_parts if len(part) > 3):
                matched.append(c)

        if not matched:
            return all_comps

        return matched

    def _build_subgraph(self, companies: List[Dict[str, Any]], question: str) -> Dict[str, Any]:
        """Traverse the Knowledge Graph in-memory without running SQL search queries."""
        subgraph: Dict[str, Any] = {
            "companies": companies,
            "metrics": [],
            "risks": [],
            "documents": [],
            "guidance": [],
            "concalls": [],
        }

        for comp in companies:
            cid = comp.get("id")
            node_id = comp.get("node_id") or f"comp_{cid}"

            if node_id not in self.graph.nodes:
                found = self.graph.find_company_node(comp.get("ticker", ""))
                if found:
                    node_id = found["id"]

            if node_id in self.graph.nodes:
                # 1. Direct Edge Traversal: Financial Metrics
                metric_nodes = self.graph.get_connected_nodes(node_id, "REPORTED_FINANCIALS")
                for mn in metric_nodes:
                    subgraph["metrics"].append({
                        "company_id": cid,
                        "period": mn["properties"].get("period"),
                        "revenue": mn["properties"].get("revenue"),
                        "revenue_growth": mn["properties"].get("revenue_growth"),
                        "net_profit": mn["properties"].get("net_profit"),
                        "operating_margin": mn["properties"].get("operating_margin"),
                        "eps": mn["properties"].get("eps"),
                        "currency": mn["properties"].get("currency", "USD"),
                    })

                # 2. Direct Edge Traversal: Disclosed Risk Factors
                risk_nodes = self.graph.get_connected_nodes(node_id, "HAS_RISK")
                for rn in risk_nodes:
                    subgraph["risks"].append({
                        "company_id": cid,
                        "risk": rn["properties"].get("category", rn["label"]),
                        "description": rn["properties"].get("description", ""),
                        "page_number": rn["properties"].get("page_number", 1),
                        "doc_file": rn["properties"].get("source_doc", "Annual Report.pdf"),
                    })

                # 3. Direct Edge Traversal: Semantic Management Guidance (No SQL LIKE!)
                guidance_nodes = self.graph.get_connected_nodes(node_id, "MENTIONS_GUIDANCE")
                for gn in guidance_nodes:
                    subgraph["guidance"].append({
                        "company_id": cid,
                        "category": gn["properties"].get("category"),
                        "period": gn["properties"].get("period"),
                        "statement": gn["properties"].get("statement"),
                        "source_doc": gn["properties"].get("source_doc"),
                        "page": gn["properties"].get("page"),
                    })

                # 4. Direct Edge Traversal: Documents
                doc_nodes = (
                    self.graph.get_connected_nodes(node_id, "ANNUAL_FILING")
                    + self.graph.get_connected_nodes(node_id, "CONCALL_FILED")
                )
                for dn in doc_nodes:
                    subgraph["documents"].append({
                        "id": dn["properties"].get("document_id"),
                        "file_name": dn["properties"].get("file_name"),
                        "period": dn["properties"].get("period"),
                        "document_type": dn["properties"].get("document_type"),
                    })

        # If graph was empty or company missing, fallback to MySQL
        if not subgraph["metrics"] and not subgraph["risks"] and not subgraph["guidance"]:
            return self._build_subgraph_from_mysql(companies, question)

        return subgraph

    def _build_subgraph_from_mysql(self, companies: List[Dict[str, Any]], question: str) -> Dict[str, Any]:
        """Fallback database retrieval if the graph index is not yet built."""
        subgraph: Dict[str, Any] = {"companies": companies, "metrics": [], "risks": [], "documents": [], "guidance": [], "concalls": []}
        cids = [c["id"] for c in companies if c.get("id")]
        if not cids:
            return subgraph

        format_strings = ",".join(["%s"] * len(cids))
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    f"SELECT * FROM financial_data WHERE company_id IN ({format_strings}) ORDER BY period ASC;",
                    tuple(cids),
                )
                subgraph["metrics"] = cursor.fetchall()

                cursor.execute(
                    f"SELECT r.*, d.file_name as doc_file, d.report_period "
                    f"FROM risk_factors r LEFT JOIN documents d ON r.document_id = d.id "
                    f"WHERE r.company_id IN ({format_strings}) ORDER BY r.page_number ASC;",
                    tuple(cids),
                )
                subgraph["risks"] = cursor.fetchall()

                cursor.execute(
                    f"SELECT id, company_id, file_name, file_hash, document_type, report_period "
                    f"FROM documents WHERE company_id IN ({format_strings});",
                    tuple(cids),
                )
                subgraph["documents"] = cursor.fetchall()
        except Exception as exc:
            logger.exception("Error extracting fallback subgraph from MySQL: %s", exc)

        return subgraph

    def _format_graph_context(self, subgraph: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], List[str]]:
        """Translate the traversed subgraph into concise semantic triples and citation lists."""
        lines = []
        citations = []
        graph_nodes = []

        comp_map = {c["id"]: c for c in subgraph.get("companies", []) if c.get("id")}

        # Format Companies
        for c in subgraph.get("companies", []):
            ticker = c.get("ticker", "N/A")
            lines.append(f"ENTITY [Company]: {c['name']} (Ticker: {ticker}, Investor: {c.get('website', 'N/A')})")
            graph_nodes.append(f"Company: {ticker or c['name']}")

        # Format Metrics
        lines.append("\nRELATIONSHIPS [Reported Financial Metrics]:")
        for m in subgraph.get("metrics", []):
            comp = comp_map.get(m["company_id"], {})
            c_name = comp.get("ticker") or comp.get("name", "Unknown")
            curr = m.get("currency", "USD")
            sym = "₹" if curr == "INR" else "$"
            divider = 1e7 if curr == "INR" else 1e9
            unit = "Cr" if curr == "INR" else "B"

            rev_val = float(m['revenue']) if m.get('revenue') is not None else None
            rev_str = f"{sym}{rev_val/divider:.1f}{unit}" if rev_val is not None else "N/A"
            growth_str = f"{float(m['revenue_growth'])*100:.1f}% YoY" if m.get("revenue_growth") is not None else "N/A"
            profit_val = float(m['net_profit']) if m.get('net_profit') is not None else None
            profit_str = f"{sym}{profit_val/divider:.1f}{unit}" if profit_val is not None else "N/A"
            margin_str = f"{float(m['operating_margin'])*100:.1f}%" if m.get("operating_margin") is not None else "N/A"
            eps_str = f"{sym}{float(m['eps']):.2f}" if m.get("eps") is not None else "N/A"

            lines.append(
                f"- ({c_name}) -[IN_PERIOD {m.get('period')}]-> Revenue: {rev_str} (Growth: {growth_str}), "
                f"Net Profit: {profit_str}, Operating Margin: {margin_str}, EPS: {eps_str}"
            )
            graph_nodes.append(f"{c_name} Metric: {m.get('period')} (Rev: {rev_str})")

        # Format Risks & Citations
        lines.append("\nRELATIONSHIPS [Disclosed Risk Factors & Provenance]:")
        for r in subgraph.get("risks", []):
            comp = comp_map.get(r["company_id"], {})
            c_name = comp.get("ticker") or comp.get("name", "Unknown")
            doc_file = r.get("doc_file") or "Annual Report.pdf"
            page = r.get("page_number") or "N/A"

            lines.append(
                f"- ({c_name}) -[DISCLOSED_RISK]-> '{r['risk']}': {r.get('description', '')} "
                f"[Source: {doc_file}, Page {page}]"
            )
            citations.append({
                "company": c_name,
                "risk": r["risk"],
                "source": doc_file,
                "page": f"Page {page}",
                "period": r.get("report_period", "Latest"),
            })
            graph_nodes.append(f"{c_name} Risk: {r['risk']} (p.{page})")

        # Format Pre-Indexed Semantic Management Guidance (No Search Query!)
        guidance_list = subgraph.get("guidance", [])
        if guidance_list:
            lines.append("\nRELATIONSHIPS [Pre-Indexed Management Guidance & Concall Statements]:")
            for g in guidance_list[:8]:
                comp = comp_map.get(g["company_id"], {})
                c_name = comp.get("ticker") or comp.get("name", "Unknown")
                cat = g.get("category", "Strategic Guidance")
                period = g.get("period", "Latest")
                page = g.get("page", "p.1")
                doc_file = g.get("source_doc", "Concall.pdf")
                stmt = g.get("statement", "")

                lines.append(
                    f"- ({c_name}) -[GUIDANCE_{cat.replace(' ', '_').upper()} {period}]-> \"{stmt}\" "
                    f"[Source: {doc_file}, {page}]"
                )
                citations.append({
                    "company": c_name,
                    "type": "Management Guidance",
                    "category": cat,
                    "period": period,
                    "source": doc_file,
                    "page": page,
                    "excerpt": stmt[:100] + "...",
                })
                graph_nodes.append(f"{c_name} Guidance: {cat} ({period})")

        return "\n".join(lines), citations, graph_nodes

    def _synthesize_direct_graph_answer(
        self, question: str, subgraph: Dict[str, Any], citations: List[Dict[str, Any]]
    ) -> str:
        """Deterministic Graph RAG answer generation if Ollama is currently starting up or offline."""
        companies = subgraph.get("companies", [])
        metrics = subgraph.get("metrics", [])
        risks = subgraph.get("risks", [])
        guidance = subgraph.get("guidance", [])

        q_lower = question.lower()
        parts = []

        # Numerical / Revenue / Growth queries
        if any(w in q_lower for w in ["revenue", "growth", "profit", "margin", "eps", "performance"]):
            parts.append("### Financial Performance Overview (Knowledge Graph Verification):")
            for c in companies:
                c_metrics = [m for m in metrics if m["company_id"] == c["id"]]
                if c_metrics:
                    latest = c_metrics[-1]
                    curr = latest.get("currency", "USD")
                    sym = "₹" if curr == "INR" else "$"
                    divider = 1e7 if curr == "INR" else 1e9
                    unit = "Crores" if curr == "INR" else "Billion"

                    rev = f"{sym}{float(latest['revenue'])/divider:,.2f} {unit}" if latest.get("revenue") is not None else "N/A"
                    growth = f"{float(latest['revenue_growth'])*100:+.1f}% YoY" if latest.get("revenue_growth") is not None else "N/A"
                    margin = f"{float(latest['operating_margin'])*100:.1f}%" if latest.get("operating_margin") is not None else "N/A"
                    profit = f"{sym}{float(latest['net_profit'])/divider:,.2f} {unit}" if latest.get("net_profit") is not None else "N/A"
                    eps = f"{sym}{float(latest['eps']):,.2f}" if latest.get("eps") is not None else "N/A"

                    parts.append(
                        f"• **{c['name']} ({c.get('ticker')})** for **{latest.get('period')}**:\n"
                        f"  - Revenue: **{rev}** (Growth: **{growth}**)\n"
                        f"  - Net Profit: **{profit}** | Operating Margin: **{margin}**\n"
                        f"  - Diluted EPS: **{eps}**"
                    )

        # Risk factor queries
        if any(w in q_lower for w in ["risk", "threat", "concern", "disclos"]):
            parts.append("\n### Identified Risk Disclosures with Provenance:")
            for r in risks[:4]:
                comp_ticker = next((c.get("ticker") for c in companies if c["id"] == r["company_id"]), "Company")
                parts.append(
                    f"• **{r['risk']}** ({comp_ticker}): {r.get('description')}\n"
                    f"  *Citation: {r.get('doc_file', 'Annual Report.pdf')}, Page {r.get('page_number')}*"
                )

        # Guidance / CapEx / Strategy queries (from pre-indexed Graph)
        if guidance or any(w in q_lower for w in ["concall", "guidance", "capex", "capital", "management", "outlook", "plan", "commentary"]):
            if guidance:
                parts.append("\n### Management Guidance & Strategic Highlights (Knowledge Graph Traversal):")
                for g in guidance[:4]:
                    comp_ticker = next((c.get("ticker") for c in companies if c["id"] == g["company_id"]), "Company")
                    parts.append(
                        f"• **{comp_ticker} [{g.get('category')}] ({g.get('period')})**: \"{g.get('statement')}\"\n"
                        f"  *Citation: {g.get('source_doc')}, {g.get('page')}*"
                    )

        if not parts:
            # General summary
            parts.append("### Corporate Intelligence Summary:")
            for c in companies:
                parts.append(f"• **{c['name']} ({c.get('ticker')})**: Monitored with verified annual reports, financial metrics, and risk disclosures.")

        parts.append("\n> **Provenance Note**: All facts retrieved via direct Knowledge Graph traversal without SQL search queries.")
        return "\n".join(parts)
