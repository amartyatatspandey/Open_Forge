"""Unit tests for src/knowledge_graph/admin/ package.

Tests DesignMethodology management API and CLI.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.knowledge_graph import KnowledgeGraph
from src.knowledge_graph.admin import (
    DEFAULT_METHODOLOGIES,
    add_methodology,
    get_methodology,
    list_methodologies,
    seed_default_methodologies,
)
from src.knowledge_graph.admin.cli import main
from src.schemas.datasheet import ExtractionMethod
from src.schemas.kg import KGNode, KGNodeType


class TestAddMethodology:
    """Tests for add_methodology function."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock Config."""
        config = MagicMock()
        config.graph_path = MagicMock()
        return config

    def test_add_methodology_creates_node_with_layer_5(self, mock_config: MagicMock) -> None:
        """add_methodology creates node with layer=5, confidence=1.0."""
        graph = KnowledgeGraph()

        node = add_methodology(
            graph=graph,
            name="test_methodology",
            triggers=["trigger1", "trigger2"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={"layers": 2},
            config=mock_config,
        )

        assert node.layer == 5
        assert node.confidence == 1.0
        assert node.node_type == KGNodeType.DESIGN_METHODOLOGY
        assert node.extraction_method == ExtractionMethod.MANUAL

    def test_add_methodology_is_idempotent(self, mock_config: MagicMock) -> None:
        """add_methodology is idempotent (run twice → no duplicate)."""
        graph = KnowledgeGraph()

        # First call
        node1 = add_methodology(
            graph=graph,
            name="idempotent_test",
            triggers=["a", "b"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={"layers": 2},
            config=mock_config,
        )

        # Second call with same name (updated triggers)
        node2 = add_methodology(
            graph=graph,
            name="idempotent_test",
            triggers=["a", "b", "c"],  # Different triggers
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={"layers": 2},
            config=mock_config,
        )

        # Should have same ID
        assert node1.id == node2.id

        # Should only be one node in graph
        methodologies = list_methodologies(graph)
        assert len(methodologies) == 1

    def test_add_methodology_creates_correct_node_id(self, mock_config: MagicMock) -> None:
        """Node ID follows pattern design_methodology:{normalized_name}."""
        graph = KnowledgeGraph()

        node = add_methodology(
            graph=graph,
            name="My Methodology",
            triggers=["test"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={},
            config=mock_config,
        )

        assert node.id == "design_methodology:my_methodology"


class TestListMethodologies:
    """Tests for list_methodologies function."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock Config."""
        config = MagicMock()
        config.graph_path = MagicMock()
        return config

    def test_list_methodologies_returns_only_design_methodology_nodes(self, mock_config: MagicMock) -> None:
        """list_methodologies returns only DESIGN_METHODOLOGY nodes."""
        graph = KnowledgeGraph()

        # Add some methodology nodes
        add_methodology(
            graph=graph,
            name="method1",
            triggers=["a"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={},
            config=mock_config,
        )
        add_methodology(
            graph=graph,
            name="method2",
            triggers=["b"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={},
            config=mock_config,
        )

        # Add a non-methodology node manually
        other_node = KGNode(
            id="component_type:test",
            node_type=KGNodeType.COMPONENT_TYPE,
            layer=2,
            label="Test Component",
            properties={},
            source="test",
            confidence=0.9,
            extraction_method=ExtractionMethod.MANUAL,
            created_at="2026-01-01T00:00:00Z",
        )
        graph.add_node(other_node)

        # List should only return methodology nodes
        methodologies = list_methodologies(graph)

        assert len(methodologies) == 2
        for node in methodologies:
            assert node.node_type == KGNodeType.DESIGN_METHODOLOGY

    def test_list_methodologies_sorted_by_label(self, mock_config: MagicMock) -> None:
        """list_methodologies returns nodes sorted by label."""
        graph = KnowledgeGraph()

        # Add in non-alphabetical order
        for name in ["zebra", "alpha", "beta"]:
            add_methodology(
                graph=graph,
                name=name,
                triggers=[name],
                active_constraint_types=["proximity"],
                suppressed_constraint_types=[],
                board_spec_defaults={},
                config=mock_config,
            )

        methodologies = list_methodologies(graph)

        labels = [n.label for n in methodologies]
        assert labels == ["alpha", "beta", "zebra"]

    def test_list_methodologies_empty_graph(self) -> None:
        """list_methodologies returns empty list for empty graph."""
        graph = KnowledgeGraph()

        methodologies = list_methodologies(graph)

        assert methodologies == []


class TestGetMethodology:
    """Tests for get_methodology function."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock Config."""
        config = MagicMock()
        config.graph_path = MagicMock()
        return config

    def test_get_methodology_returns_none_for_unknown_name(self, mock_config: MagicMock) -> None:
        """get_methodology returns None for unknown name."""
        graph = KnowledgeGraph()

        # Add one methodology
        add_methodology(
            graph=graph,
            name="existing",
            triggers=["test"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={},
            config=mock_config,
        )

        # Try to get non-existent
        result = get_methodology(graph, "nonexistent")

        assert result is None

    def test_get_methodology_returns_correct_node(self, mock_config: MagicMock) -> None:
        """get_methodology returns correct node by name."""
        graph = KnowledgeGraph()

        add_methodology(
            graph=graph,
            name="power_mgmt",
            triggers=["buck", "boost"],
            active_constraint_types=["proximity", "keepout"],
            suppressed_constraint_types=[],
            board_spec_defaults={"layers": 4},
            config=mock_config,
        )

        node = get_methodology(graph, "power_mgmt")

        assert node is not None
        assert node.label == "power_mgmt"
        assert node.properties["triggers"] == ["buck", "boost"]


class TestSeedDefaultMethodologies:
    """Tests for seed_default_methodologies function."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock Config."""
        config = MagicMock()
        config.graph_path = MagicMock()
        return config

    def test_seed_default_methodologies_creates_exactly_5_nodes(self, mock_config: MagicMock) -> None:
        """seed_default_methodologies creates exactly 5 nodes."""
        graph = KnowledgeGraph()

        count = seed_default_methodologies(graph, mock_config)

        assert count == 5

        # Verify all 5 are in graph
        methodologies = list_methodologies(graph)
        assert len(methodologies) == 5

    def test_seed_default_methodologies_is_idempotent(self, mock_config: MagicMock) -> None:
        """seed_default_methodologies is idempotent."""
        graph = KnowledgeGraph()

        # First seed
        count1 = seed_default_methodologies(graph, mock_config)
        assert count1 == 5

        # Second seed - should update, not duplicate
        count2 = seed_default_methodologies(graph, mock_config)
        assert count2 == 5

        # Should still only have 5 nodes
        methodologies = list_methodologies(graph)
        assert len(methodologies) == 5

    def test_seed_rf_highfreq_has_antenna_in_triggers(self, mock_config: MagicMock) -> None:
        """Verify 'RF_highfreq' node has 'antenna' in triggers property."""
        graph = KnowledgeGraph()

        seed_default_methodologies(graph, mock_config)

        rf_node = get_methodology(graph, "RF_highfreq")
        assert rf_node is not None
        assert "antenna" in rf_node.properties["triggers"]

    def test_seed_power_management_has_expected_constraint_types(self, mock_config: MagicMock) -> None:
        """Verify constraint_types are stored (not node IDs) in active_constraint_types."""
        graph = KnowledgeGraph()

        seed_default_methodologies(graph, mock_config)

        power_node = get_methodology(graph, "power_management")
        assert power_node is not None

        active_types = power_node.properties["active_constraint_types"]
        # Should be constraint type strings, not node IDs
        assert "proximity" in active_types
        assert "orientation" in active_types
        assert "group" in active_types

        # Should NOT contain node ID patterns
        for t in active_types:
            assert ":" not in t, f"Constraint type '{t}' looks like a node ID"

    def test_seed_all_default_methodologies_have_valid_structure(self, mock_config: MagicMock) -> None:
        """Verify all default methodologies have required properties."""
        graph = KnowledgeGraph()

        seed_default_methodologies(graph, mock_config)

        for name in DEFAULT_METHODOLOGIES.keys():
            node = get_methodology(graph, name)
            assert node is not None, f"Methodology {name} not found"
            assert node.layer == 5
            assert node.node_type == KGNodeType.DESIGN_METHODOLOGY

            # Check required properties exist
            props = node.properties
            assert "triggers" in props
            assert "active_constraint_types" in props
            assert "suppressed_constraint_types" in props
            assert "board_spec_defaults" in props

            # Check board_spec_defaults has expected keys
            board_specs = props["board_spec_defaults"]
            assert "layers" in board_specs
            assert "material" in board_specs


class TestCLI:
    """Tests for admin CLI."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock Config."""
        config = MagicMock()
        config.graph_path = MagicMock()
        return config

    @patch("src.knowledge_graph.admin.cli._get_config")
    @patch("src.knowledge_graph.admin.cli._load_graph")
    @patch("src.knowledge_graph.admin.cli._save_graph")
    def test_cli_list_command(self, mock_save, mock_load, mock_get_config, mock_config: MagicMock) -> None:
        """CLI list command prints methodology names and trigger counts."""
        mock_get_config.return_value = mock_config

        # Setup mock graph with methodologies
        graph = KnowledgeGraph()
        from src.knowledge_graph.admin.methodologies import add_methodology
        add_methodology(
            graph=graph,
            name="test_method",
            triggers=["a", "b", "c"],
            active_constraint_types=["proximity"],
            suppressed_constraint_types=[],
            board_spec_defaults={},
            config=mock_config,
        )
        mock_load.return_value = graph

        # Run CLI
        result = main(["list"])

        assert result == 0

    @patch("src.knowledge_graph.admin.cli._get_config")
    @patch("src.knowledge_graph.admin.cli._load_graph")
    def test_cli_show_command_not_found(self, mock_load, mock_get_config, mock_config: MagicMock) -> None:
        """CLI show command returns error for unknown methodology."""
        mock_get_config.return_value = mock_config
        mock_load.return_value = KnowledgeGraph()

        result = main(["show", "nonexistent"])

        assert result == 1

    @patch("src.knowledge_graph.admin.cli._get_config")
    @patch("src.knowledge_graph.admin.cli._load_graph")
    @patch("src.knowledge_graph.admin.cli._save_graph")
    def test_cli_seed_command(self, mock_save, mock_load, mock_get_config, mock_config: MagicMock, capsys) -> None:
        """CLI seed command runs seed_default_methodologies and prints count."""
        mock_get_config.return_value = mock_config
        mock_load.return_value = KnowledgeGraph()

        result = main(["seed"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Seeded 5 methodologies" in captured.out or "5" in captured.out

    @patch("src.knowledge_graph.admin.cli._get_config")
    @patch("src.knowledge_graph.admin.cli._load_graph")
    @patch("src.knowledge_graph.admin.cli._save_graph")
    def test_cli_add_command(self, mock_save, mock_load, mock_get_config, mock_config: MagicMock, capsys) -> None:
        """CLI add command calls add_methodology and prints confirmation."""
        mock_get_config.return_value = mock_config
        mock_load.return_value = KnowledgeGraph()

        result = main([
            "add",
            "--name", "custom_cli",
            "--triggers", "led,driver,pwm",
            "--active", "proximity,orientation",
            "--suppress", "",
            "--board-specs", "layers=4,material=FR4",
        ])

        assert result == 0
        captured = capsys.readouterr()
        assert "Added methodology: custom_cli" in captured.out or "custom_cli" in captured.out

    def test_cli_no_command_prints_help(self, capsys) -> None:
        """CLI with no command prints help."""
        result = main([])

        assert result == 1
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "kg-admin" in captured.err.lower()
