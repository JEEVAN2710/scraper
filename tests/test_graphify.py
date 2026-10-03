"""Unit tests for the KnowledgeGraph and Graphifier module."""

import json
from pathlib import Path
import pytest

from app.pipeline.graphify import Graphifier, KnowledgeGraph


def test_knowledge_graph_node_and_edge_operations(tmp_path: Path):
    """Verify node creation, edge linking, and adjacency indices."""
    graph_path = tmp_path / "test_graph.json"
    kg = KnowledgeGraph(storage_path=graph_path)

    # 1. Add Company Node
    comp_node = kg.add_node(
        node_id="comp_10",
        label="TESTCO",
        node_type="company",
        properties={"company_id": 10, "name": "Test Corporation", "ticker": "TESTCO"},
    )
    assert comp_node["id"] == "comp_10"
    assert comp_node["type"] == "company"

    # 2. Add Metric Node
    metric_node = kg.add_node(
        node_id="metric_1",
        label="FY2025: $10B",
        node_type="metric",
        properties={"period": "FY2025", "revenue": 10000000000.0},
    )
    assert metric_node["id"] == "metric_1"

    # 3. Add Edge
    edge = kg.add_edge("comp_10", "metric_1", "REPORTED_FINANCIALS", {"period": "FY2025"})
    assert edge is not None
    assert edge["source"] == "comp_10"
    assert edge["target"] == "metric_1"
    assert edge["label"] == "REPORTED_FINANCIALS"

    # 4. Traversal
    outgoing = kg.get_outgoing_edges("comp_10")
    assert len(outgoing) == 1
    assert outgoing[0]["target"] == "metric_1"

    connected = kg.get_connected_nodes("comp_10", "REPORTED_FINANCIALS")
    assert len(connected) == 1
    assert connected[0]["id"] == "metric_1"

    # 5. Lookup by Ticker and Substring
    found_ticker = kg.find_company_node("TESTCO")
    assert found_ticker is not None
    assert found_ticker["id"] == "comp_10"

    found_name = kg.find_company_node("Test Corporation")
    assert found_name is not None
    assert found_name["id"] == "comp_10"


def test_knowledge_graph_serialization_and_persistence(tmp_path: Path):
    """Verify saving to and loading from JSON file."""
    graph_path = tmp_path / "saved_graph.json"
    kg = KnowledgeGraph(storage_path=graph_path)

    kg.add_node("comp_1", "ACME", "company", {"ticker": "ACME", "name": "Acme Inc"})
    kg.add_node("risk_1", "Supply Chain", "risk", {"category": "Supply Chain"})
    kg.add_edge("comp_1", "risk_1", "HAS_RISK")

    # Save
    saved_path = kg.save_to_disk()
    assert saved_path.exists()

    # Load in a fresh instance
    kg2 = KnowledgeGraph(storage_path=saved_path)
    loaded = kg2.load_from_disk()
    assert loaded is True
    assert len(kg2.nodes) == 2
    assert len(kg2.edges) == 1
    assert kg2.find_company_node("ACME") is not None


def test_semantic_guidance_extraction():
    """Verify domain heuristic extraction of strategic guidance and capex statements."""
    graphifier = Graphifier()
    sample_chunks = [
        {
            "id": 1,
            "company_id": 5,
            "document_id": 2,
            "ticker": "ADANIENT",
            "report_period": "Apr 2026",
            "page_start": 4,
            "page_end": 4,
            "file_name": "Concall_Apr_2026.pdf",
            "content": (
                "Regarding our capital expenditure, the total capex incurred across airports "
                "and solar projects is approximately 10000 crores for this fiscal year. "
                "We expect to grow our consolidated EBITDA by 20% over the next two years."
            ),
        },
        {
            "id": 2,
            "company_id": 5,
            "document_id": 2,
            "ticker": "ADANIENT",
            "report_period": "Apr 2026",
            "page_start": 5,
            "page_end": 5,
            "file_name": "Concall_Apr_2026.pdf",
            "content": "Short text.",  # Should be skipped due to length
        },
    ]

    guidance = graphifier.extract_semantic_guidance(sample_chunks)
    assert len(guidance) >= 1

    capex_item = next((g for g in guidance if "CapEx" in g["category"] or "Revenue" in g["category"]), None)
    assert capex_item is not None
    assert "ADANIENT" in capex_item["ticker"]
    assert "Page 4" in capex_item["page"]


def test_company_subgraph_traversal(tmp_path: Path):
    """Verify 1-hop and 2-hop neighborhood extraction for a company."""
    kg = KnowledgeGraph(storage_path=tmp_path / "subgraph.json")

    kg.add_node("comp_1", "INFY", "company", {"company_id": 1, "ticker": "INFY", "name": "Infosys"})
    kg.add_node("doc_1", "Report FY24", "document", {"document_id": 1, "file_name": "infy.pdf"})
    kg.add_node("fin_1", "FY24: $18B", "metric", {"revenue": 18000000000})
    kg.add_node("risk_1", "Forex", "risk", {"category": "Forex"})

    kg.add_edge("comp_1", "doc_1", "ANNUAL_FILING")
    kg.add_edge("comp_1", "fin_1", "REPORTED_FINANCIALS")
    kg.add_edge("comp_1", "risk_1", "HAS_RISK")
    kg.add_edge("doc_1", "fin_1", "EVIDENCES")

    subgraph = kg.get_company_subgraph("comp_1")
    assert len(subgraph["nodes"]) == 4
    assert len(subgraph["edges"]) == 4
    assert subgraph["company"]["id"] == "comp_1"
