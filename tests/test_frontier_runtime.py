from __future__ import annotations

from pathlib import Path

from abel_alpha import narrative_impl as ni


def _seed_discovery() -> dict:
    return {
        "ticker": "TSLA",
        "target_asset": "TSLA",
        "target_node": "TSLA.price",
        "source": "abel_live",
        "parents": [
            {"node_id": "AAPL.price", "ticker": "AAPL", "field": "price", "roles": ["parent"]},
        ],
        "blanket_new": [
            {"node_id": "TSLA.volume", "ticker": "TSLA", "field": "volume", "roles": ["sibling"]},
        ],
        "children": [
            {"node_id": "BTCUSD.price", "ticker": "BTCUSD", "field": "price"},
        ],
        "K_discovery": 1,
        "backtest": {"start": "2020-01-01"},
        "created_at": "2026-04-22T00:00:00+00:00",
    }


def test_frontier_state_from_discovery_preserves_field_aware_nodes() -> None:
    frontier = ni.frontier_state_from_discovery(_seed_discovery())

    nodes = {item["node_id"]: item for item in frontier["nodes"]}

    assert frontier["target_node"] == "TSLA.price"
    assert set(nodes) == {"TSLA.price", "AAPL.price", "TSLA.volume", "BTCUSD.price"}
    assert nodes["TSLA.volume"]["depth"] == 1
    assert "sibling" in nodes["TSLA.volume"]["discovery_roles"]
    assert nodes["BTCUSD.price"]["discovered_from"] == ["TSLA.price"]


def test_init_branch_prefers_frontier_nodes_for_default_inputs(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v1", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    branch = ni.init_branch_dir(session, "graph-v1")
    spec = ni.load_branch_spec(branch)

    assert spec["target_node"] == "TSLA.price"
    assert spec["suggested_inputs"][0]["node_id"] == "TSLA.volume"
    assert spec["selected_inputs"][0]["node_id"] == "TSLA.volume"


def test_expand_frontier_command_merges_new_nodes_without_duplicates(tmp_path: Path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v2", tmp_path / "research")
    discovery = {
        "ticker": "TSLA",
        "target_asset": "TSLA",
        "target_node": "TSLA.price",
        "source": "abel_live",
        "parents": [{"node_id": "AAPL.price", "ticker": "AAPL", "field": "price"}],
        "blanket_new": [],
        "children": [],
        "K_discovery": 1,
        "backtest": {"start": "2020-01-01"},
        "created_at": "2026-04-22T00:00:00+00:00",
    }
    ni.write_discovery(session, discovery)
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(discovery))

    monkeypatch.setattr(
        ni,
        "fetch_live_graph_payload",
        lambda node_id, limit: {
            "ticker": "AAPL",
            "target_asset": "AAPL",
            "target_node": "AAPL.price",
            "source": "abel_live",
            "parents": [{"node_id": "MSFT.price", "ticker": "MSFT", "field": "price"}],
            "blanket_new": [
                {"node_id": "TSLA.volume", "ticker": "TSLA", "field": "volume", "roles": ["sibling"]},
            ],
            "children": [],
            "K_discovery": 1,
            "created_at": "2026-04-22T00:10:00+00:00",
        },
    )

    result = ni.expand_frontier_command(session=session, from_node="AAPL.price", limit=8)

    frontier = ni.load_frontier_state(session)
    nodes = [item["node_id"] for item in frontier["nodes"]]

    assert result == 0
    assert nodes.count("TSLA.volume") == 1
    assert "MSFT.price" in nodes
    assert len(frontier["expansions"]) == 1
    assert frontier["expansions"][0]["from_node"] == "AAPL.price"


def test_render_session_includes_graph_frontier_section(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v3", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    ni.render_session(session)

    readme = (session / "README.md").read_text(encoding="utf-8")
    assert "## Graph Frontier" in readme
    assert "TSLA.volume" in readme


def test_probe_nodes_command_updates_frontier_availability(tmp_path: Path, monkeypatch) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v4", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))

    monkeypatch.setattr(
        ni,
        "run_edge_probe_data",
        lambda **kwargs: {
            "target": {"node_id": "TSLA.price"},
            "requested_window": {"start": "2020-01-01", "end": None},
            "basket": {"dense_overlap_start": "2020-01-03T00:00:00+00:00", "limiting_inputs": ["BTCUSD.price"]},
            "results": [
                {
                    "node_id": "BTCUSD.price",
                    "status": "partial_target_overlap",
                    "row_count": 3,
                    "native_window": {
                        "start": "2020-01-03T00:00:00+00:00",
                        "end": "2020-01-05T00:00:00+00:00",
                    },
                    "target_overlap_days": 2,
                    "target_decision_days": 3,
                    "first_usable_target_time": "2020-01-03T00:00:00+00:00",
                }
            ],
        },
    )

    result = ni.probe_nodes_command(
        session=session,
        node_ids=["BTCUSD.price"],
        start=None,
        end=None,
        limit=500,
    )

    frontier = ni.load_frontier_state(session)
    btc_entry = ni.find_frontier_entry(frontier, "BTCUSD.price")

    assert result == 0
    assert frontier["probe_history"][-1]["node_ids"] == ["BTCUSD.price"]
    assert btc_entry is not None
    assert btc_entry["availability_summary"]["status"] == "partial_target_overlap"
    assert btc_entry["availability_summary"]["target_overlap_days"] == 2


def test_select_branch_inputs_command_updates_branch_spec_from_frontier(tmp_path: Path) -> None:
    session = ni.init_session_dir("TSLA", "frontier-v5", tmp_path / "research")
    ni.write_discovery(session, _seed_discovery())
    ni.write_frontier_state(session, ni.frontier_state_from_discovery(_seed_discovery()))
    branch = ni.init_branch_dir(session, "graph-v1")

    result = ni.select_branch_inputs_command(
        branch=branch,
        node_ids=["BTCUSD.price"],
        replace=True,
    )

    spec = ni.load_branch_spec(branch)

    assert result == 0
    assert spec["selected_inputs"] == [
        {"node_id": "BTCUSD.price", "asset": "BTCUSD", "field": "price"}
    ]
