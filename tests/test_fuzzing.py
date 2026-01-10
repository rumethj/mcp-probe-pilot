"""Tests for the fuzzing module.

This module tests the fuzzing strategies and FuzzScenarioGenerator
to ensure they correctly generate fuzz values and scenarios.
"""

import math
import sys

import pytest

from mcp_probe_pilot.fuzzing import (
    BaseFuzzStrategy,
    BoundaryValueStrategy,
    DEFAULT_STRATEGIES,
    FuzzCategory,
    FuzzScenarioGenerator,
    FuzzValue,
    InvalidTypeStrategy,
    NullMissingStrategy,
    is_omit_parameter,
)
from mcp_probe_pilot.generators.models import (
    GeneratedScenario,
    GroundTruthSpec,
    ScenarioCategory,
    ScenarioSet,
    TargetType,
)


# =============================================================================
# FuzzValue Model Tests
# =============================================================================


class TestFuzzValue:
    """Tests for FuzzValue model."""

    def test_fuzz_value_creation(self):
        """Test creating a FuzzValue instance."""
        fuzz = FuzzValue(
            value="wrong_type",
            param_name="count",
            original_type="integer",
            fuzz_category=FuzzCategory.INVALID_TYPE,
            description="String instead of integer",
        )
        assert fuzz.value == "wrong_type"
        assert fuzz.param_name == "count"
        assert fuzz.original_type == "integer"
        assert fuzz.fuzz_category == FuzzCategory.INVALID_TYPE
        assert fuzz.expected_error is True
        assert fuzz.expected_error_code == -32602

    def test_fuzz_value_custom_error_code(self):
        """Test FuzzValue with custom error code."""
        fuzz = FuzzValue(
            value=None,
            param_name="name",
            original_type="string",
            fuzz_category=FuzzCategory.NULL_MISSING,
            description="Null value",
            expected_error_code=-32600,
        )
        assert fuzz.expected_error_code == -32600


class TestFuzzCategory:
    """Tests for FuzzCategory enum."""

    def test_fuzz_categories_exist(self):
        """Test that all expected categories exist."""
        assert FuzzCategory.INVALID_TYPE == "invalid_type"
        assert FuzzCategory.BOUNDARY_VALUE == "boundary_value"
        assert FuzzCategory.NULL_MISSING == "null_missing"


# =============================================================================
# InvalidTypeStrategy Tests
# =============================================================================


class TestInvalidTypeStrategy:
    """Tests for InvalidTypeStrategy."""

    @pytest.fixture
    def strategy(self) -> InvalidTypeStrategy:
        """Provide an InvalidTypeStrategy instance."""
        return InvalidTypeStrategy()

    def test_category(self, strategy: InvalidTypeStrategy):
        """Test that strategy has correct category."""
        assert strategy.category == FuzzCategory.INVALID_TYPE

    def test_fuzz_string_param(self, strategy: InvalidTypeStrategy):
        """Test fuzzing a string parameter."""
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("name", schema)

        assert len(fuzz_values) > 0
        # Should include non-string types
        types_generated = {type(fv.value).__name__ for fv in fuzz_values}
        assert "int" in types_generated
        assert "float" in types_generated
        assert "bool" in types_generated

    def test_fuzz_integer_param(self, strategy: InvalidTypeStrategy):
        """Test fuzzing an integer parameter."""
        schema = {"type": "integer"}
        fuzz_values = strategy.generate_fuzz_values("count", schema)

        assert len(fuzz_values) > 0
        # Should include non-integer types
        types_generated = {type(fv.value).__name__ for fv in fuzz_values}
        assert "str" in types_generated
        assert "float" in types_generated

    def test_fuzz_boolean_param(self, strategy: InvalidTypeStrategy):
        """Test fuzzing a boolean parameter."""
        schema = {"type": "boolean"}
        fuzz_values = strategy.generate_fuzz_values("enabled", schema)

        assert len(fuzz_values) > 0
        # Should include string "true" which is a common mistake
        values = [fv.value for fv in fuzz_values]
        assert "true" in values

    def test_fuzz_array_param(self, strategy: InvalidTypeStrategy):
        """Test fuzzing an array parameter."""
        schema = {"type": "array"}
        fuzz_values = strategy.generate_fuzz_values("items", schema)

        assert len(fuzz_values) > 0
        # Should not include any arrays
        for fv in fuzz_values:
            assert not isinstance(fv.value, list)

    def test_fuzz_object_param(self, strategy: InvalidTypeStrategy):
        """Test fuzzing an object parameter."""
        schema = {"type": "object"}
        fuzz_values = strategy.generate_fuzz_values("data", schema)

        assert len(fuzz_values) > 0
        # Should not include any dicts
        for fv in fuzz_values:
            assert not isinstance(fv.value, dict)

    def test_all_values_have_correct_metadata(self, strategy: InvalidTypeStrategy):
        """Test that all generated values have correct metadata."""
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("test_param", schema)

        for fv in fuzz_values:
            assert fv.param_name == "test_param"
            assert fv.original_type == "string"
            assert fv.fuzz_category == FuzzCategory.INVALID_TYPE
            assert fv.expected_error is True
            assert fv.description is not None


# =============================================================================
# BoundaryValueStrategy Tests
# =============================================================================


class TestBoundaryValueStrategy:
    """Tests for BoundaryValueStrategy."""

    @pytest.fixture
    def strategy(self) -> BoundaryValueStrategy:
        """Provide a BoundaryValueStrategy instance."""
        return BoundaryValueStrategy()

    def test_category(self, strategy: BoundaryValueStrategy):
        """Test that strategy has correct category."""
        assert strategy.category == FuzzCategory.BOUNDARY_VALUE

    def test_fuzz_string_boundaries(self, strategy: BoundaryValueStrategy):
        """Test boundary values for string parameters."""
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("name", schema)

        values = [fv.value for fv in fuzz_values]
        # Should include empty string
        assert "" in values
        # Should include whitespace
        assert "   " in values

    def test_fuzz_string_with_min_length(self, strategy: BoundaryValueStrategy):
        """Test boundary values for string with minLength constraint."""
        schema = {"type": "string", "minLength": 5}
        fuzz_values = strategy.generate_fuzz_values("name", schema)

        # Should include string shorter than minLength
        short_strings = [fv for fv in fuzz_values if "shorter than minLength" in fv.description]
        assert len(short_strings) > 0
        # The short string should have length < 5
        assert len(short_strings[0].value) < 5

    def test_fuzz_string_with_max_length(self, strategy: BoundaryValueStrategy):
        """Test boundary values for string with maxLength constraint."""
        schema = {"type": "string", "maxLength": 10}
        fuzz_values = strategy.generate_fuzz_values("name", schema)

        # Should include string longer than maxLength
        long_strings = [fv for fv in fuzz_values if "longer than maxLength" in fv.description]
        assert len(long_strings) > 0
        # The long string should have length > 10
        assert len(long_strings[0].value) > 10

    def test_fuzz_integer_boundaries(self, strategy: BoundaryValueStrategy):
        """Test boundary values for integer parameters."""
        schema = {"type": "integer"}
        fuzz_values = strategy.generate_fuzz_values("count", schema)

        values = [fv.value for fv in fuzz_values]
        # Should include zero
        assert 0 in values
        # Should include negative
        assert -1 in values
        # Should include max int
        assert sys.maxsize in values
        # Should include min int
        assert -sys.maxsize - 1 in values

    def test_fuzz_integer_with_minimum(self, strategy: BoundaryValueStrategy):
        """Test boundary values for integer with minimum constraint."""
        schema = {"type": "integer", "minimum": 0}
        fuzz_values = strategy.generate_fuzz_values("count", schema)

        # Should include value below minimum
        below_min = [fv for fv in fuzz_values if "below minimum" in fv.description]
        assert len(below_min) > 0
        assert below_min[0].value < 0

    def test_fuzz_integer_with_maximum(self, strategy: BoundaryValueStrategy):
        """Test boundary values for integer with maximum constraint."""
        schema = {"type": "integer", "maximum": 100}
        fuzz_values = strategy.generate_fuzz_values("count", schema)

        # Should include value above maximum
        above_max = [fv for fv in fuzz_values if "above maximum" in fv.description]
        assert len(above_max) > 0
        assert above_max[0].value > 100

    def test_fuzz_number_boundaries(self, strategy: BoundaryValueStrategy):
        """Test boundary values for number (float) parameters."""
        schema = {"type": "number"}
        fuzz_values = strategy.generate_fuzz_values("price", schema)

        values = [fv.value for fv in fuzz_values]
        # Should include infinity
        assert float("inf") in values
        assert float("-inf") in values
        # Should include NaN (need special check)
        nan_values = [v for v in values if isinstance(v, float) and math.isnan(v)]
        assert len(nan_values) > 0

    def test_fuzz_array_boundaries(self, strategy: BoundaryValueStrategy):
        """Test boundary values for array parameters."""
        schema = {"type": "array"}
        fuzz_values = strategy.generate_fuzz_values("items", schema)

        values = [fv.value for fv in fuzz_values]
        # Should include empty array
        assert [] in values

    def test_fuzz_array_with_min_items(self, strategy: BoundaryValueStrategy):
        """Test boundary values for array with minItems constraint."""
        schema = {"type": "array", "minItems": 3}
        fuzz_values = strategy.generate_fuzz_values("items", schema)

        # Should include array shorter than minItems
        short_arrays = [fv for fv in fuzz_values if "shorter than minItems" in fv.description]
        assert len(short_arrays) > 0
        assert len(short_arrays[0].value) < 3

    def test_fuzz_object_boundaries(self, strategy: BoundaryValueStrategy):
        """Test boundary values for object parameters."""
        schema = {"type": "object"}
        fuzz_values = strategy.generate_fuzz_values("data", schema)

        values = [fv.value for fv in fuzz_values]
        # Should include empty object
        assert {} in values


# =============================================================================
# NullMissingStrategy Tests
# =============================================================================


class TestNullMissingStrategy:
    """Tests for NullMissingStrategy."""

    @pytest.fixture
    def strategy(self) -> NullMissingStrategy:
        """Provide a NullMissingStrategy instance."""
        return NullMissingStrategy()

    def test_category(self, strategy: NullMissingStrategy):
        """Test that strategy has correct category."""
        assert strategy.category == FuzzCategory.NULL_MISSING

    def test_fuzz_required_param(self, strategy: NullMissingStrategy):
        """Test fuzzing a required parameter."""
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("name", schema, is_required=True)

        # Should include null
        null_values = [fv for fv in fuzz_values if fv.value is None]
        assert len(null_values) > 0

        # Should include omit marker for required params
        omit_values = [fv for fv in fuzz_values if is_omit_parameter(fv.value)]
        assert len(omit_values) > 0

    def test_fuzz_optional_param(self, strategy: NullMissingStrategy):
        """Test fuzzing an optional parameter."""
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("name", schema, is_required=False)

        # Should include null
        null_values = [fv for fv in fuzz_values if fv.value is None]
        assert len(null_values) > 0

        # Should NOT include omit marker for optional params
        omit_values = [fv for fv in fuzz_values if is_omit_parameter(fv.value)]
        assert len(omit_values) == 0

    def test_all_values_expect_error(self, strategy: NullMissingStrategy):
        """Test that all null/missing values expect errors."""
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("name", schema, is_required=True)

        for fv in fuzz_values:
            assert fv.expected_error is True
            assert fv.expected_error_code == -32602


class TestOmitParameter:
    """Tests for omit parameter sentinel."""

    def test_is_omit_parameter_true(self):
        """Test is_omit_parameter returns True for sentinel."""
        strategy = NullMissingStrategy()
        schema = {"type": "string"}
        fuzz_values = strategy.generate_fuzz_values("name", schema, is_required=True)

        omit_values = [fv for fv in fuzz_values if is_omit_parameter(fv.value)]
        assert len(omit_values) > 0

    def test_is_omit_parameter_false(self):
        """Test is_omit_parameter returns False for normal values."""
        assert is_omit_parameter(None) is False
        assert is_omit_parameter("string") is False
        assert is_omit_parameter(123) is False
        assert is_omit_parameter({}) is False


# =============================================================================
# Default Strategies Tests
# =============================================================================


class TestDefaultStrategies:
    """Tests for default strategies list."""

    def test_default_strategies_count(self):
        """Test that default strategies include all MVP strategies."""
        assert len(DEFAULT_STRATEGIES) == 3

    def test_default_strategies_types(self):
        """Test that default strategies are correct types."""
        strategy_types = {type(s) for s in DEFAULT_STRATEGIES}
        assert InvalidTypeStrategy in strategy_types
        assert BoundaryValueStrategy in strategy_types
        assert NullMissingStrategy in strategy_types

    def test_all_strategies_are_base_strategy(self):
        """Test that all default strategies inherit from BaseFuzzStrategy."""
        for strategy in DEFAULT_STRATEGIES:
            assert isinstance(strategy, BaseFuzzStrategy)


# =============================================================================
# FuzzScenarioGenerator Tests
# =============================================================================


class TestFuzzScenarioGenerator:
    """Tests for FuzzScenarioGenerator."""

    @pytest.fixture
    def sample_ground_truth(self) -> GroundTruthSpec:
        """Provide a sample ground truth for testing."""
        return GroundTruthSpec(
            id="gt_tool_test_tool",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            expected_behavior="Test tool that does something",
            expected_output_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["name", "count"],
            },
            valid_input_examples=[
                {"input": {"name": "test", "count": 5, "enabled": True}}
            ],
            invalid_input_examples=[],
            semantic_reference="A test tool",
        )

    @pytest.fixture
    def sample_scenario(self) -> GeneratedScenario:
        """Provide a sample scenario for testing."""
        return GeneratedScenario(
            id="sc_tool_test_tool_happy_path_0",
            name="test_tool happy path",
            gherkin='Scenario: test_tool happy path\n  Given the MCP server is running\n  When I call tool "test_tool"',
            target_type=TargetType.TOOL,
            target_name="test_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_tool_test_tool",
        )

    @pytest.fixture
    def sample_scenario_set(
        self,
        sample_ground_truth: GroundTruthSpec,
        sample_scenario: GeneratedScenario,
    ) -> ScenarioSet:
        """Provide a sample scenario set for testing."""
        scenario_set = ScenarioSet()
        scenario_set.add_ground_truth(sample_ground_truth)
        scenario_set.add_scenario(sample_scenario)
        return scenario_set

    def test_generator_creation_default(self):
        """Test creating generator with default settings."""
        generator = FuzzScenarioGenerator()
        assert ScenarioCategory.HAPPY_PATH in generator.categories
        assert ScenarioCategory.EDGE_CASE in generator.categories
        assert len(generator.strategies) == 3

    def test_generator_creation_custom_categories(self):
        """Test creating generator with custom categories."""
        generator = FuzzScenarioGenerator(
            categories=[ScenarioCategory.HAPPY_PATH]
        )
        assert generator.categories == [ScenarioCategory.HAPPY_PATH]

    def test_generator_creation_custom_strategies(self):
        """Test creating generator with custom strategies."""
        strategies = [InvalidTypeStrategy()]
        generator = FuzzScenarioGenerator(strategies=strategies)
        assert len(generator.strategies) == 1
        assert isinstance(generator.strategies[0], InvalidTypeStrategy)

    def test_apply_fuzzing_generates_scenarios(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test that apply_fuzzing generates new scenarios."""
        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(sample_scenario_set)

        # Should have more scenarios than original
        assert len(fuzzed_set.scenarios) > len(sample_scenario_set.scenarios)

    def test_apply_fuzzing_preserves_original(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test that apply_fuzzing preserves original scenarios."""
        generator = FuzzScenarioGenerator()
        original_ids = {s.id for s in sample_scenario_set.scenarios}

        fuzzed_set = generator.apply_fuzzing(sample_scenario_set)

        # All original scenarios should still be present
        fuzzed_ids = {s.id for s in fuzzed_set.scenarios}
        assert original_ids.issubset(fuzzed_ids)

    def test_apply_fuzzing_generates_ground_truths(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test that apply_fuzzing generates ground truths for fuzz scenarios."""
        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(sample_scenario_set)

        # Should have more ground truths than original
        assert len(fuzzed_set.ground_truths) > len(sample_scenario_set.ground_truths)

    def test_fuzz_scenarios_reference_ground_truths(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test that fuzz scenarios reference their ground truths."""
        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(sample_scenario_set)

        # Every fuzz scenario should have a valid ground truth reference
        for scenario in fuzzed_set.scenarios:
            assert scenario.ground_truth_id in fuzzed_set.ground_truths

    def test_fuzz_ground_truths_expect_errors(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test that fuzz ground truths expect error responses."""
        generator = FuzzScenarioGenerator()
        original_gt_ids = set(sample_scenario_set.ground_truths.keys())

        fuzzed_set = generator.apply_fuzzing(sample_scenario_set)

        # Check only the new (fuzz) ground truths
        for gt_id, gt in fuzzed_set.ground_truths.items():
            if gt_id not in original_gt_ids:
                # Fuzz ground truths should mention graceful error handling
                assert "graceful" in gt.expected_behavior.lower() or \
                       "error" in gt.expected_behavior.lower()

    def test_apply_fuzzing_respects_categories(
        self,
        sample_ground_truth: GroundTruthSpec,
    ):
        """Test that apply_fuzzing only fuzzes specified categories."""
        # Create an error_case scenario
        error_scenario = GeneratedScenario(
            id="sc_tool_test_tool_error_case_0",
            name="test_tool error case",
            gherkin="Scenario: test_tool error",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            category=ScenarioCategory.ERROR_CASE,
            ground_truth_id="gt_tool_test_tool",
        )

        scenario_set = ScenarioSet()
        scenario_set.add_ground_truth(sample_ground_truth)
        scenario_set.add_scenario(error_scenario)

        # Generator that only fuzzes happy_path (not error_case)
        generator = FuzzScenarioGenerator(
            categories=[ScenarioCategory.HAPPY_PATH]
        )

        fuzzed_set = generator.apply_fuzzing(scenario_set)

        # Should not generate any fuzz scenarios (no happy_path to fuzz)
        assert len(fuzzed_set.scenarios) == len(scenario_set.scenarios)

    def test_apply_fuzzing_limits_per_param(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test that max_fuzz_per_param limits generated scenarios."""
        generator = FuzzScenarioGenerator()

        # With limit of 1
        fuzzed_set_limited = generator.apply_fuzzing(
            sample_scenario_set,
            max_fuzz_per_param=1,
        )

        # With higher limit
        fuzzed_set_more = generator.apply_fuzzing(
            sample_scenario_set,
            max_fuzz_per_param=5,
        )

        # Limited should have fewer scenarios
        assert len(fuzzed_set_limited.scenarios) <= len(fuzzed_set_more.scenarios)

    def test_get_fuzz_statistics(
        self,
        sample_scenario_set: ScenarioSet,
    ):
        """Test get_fuzz_statistics returns correct information."""
        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(sample_scenario_set)

        stats = generator.get_fuzz_statistics(sample_scenario_set, fuzzed_set)

        assert stats["original_scenarios"] == len(sample_scenario_set.scenarios)
        assert stats["fuzzed_scenarios"] == len(fuzzed_set.scenarios)
        assert stats["new_fuzz_scenarios"] > 0
        assert "strategies_used" in stats
        assert "categories_fuzzed" in stats


class TestFuzzScenarioGeneratorEdgeCases:
    """Edge case tests for FuzzScenarioGenerator."""

    def test_empty_scenario_set(self):
        """Test fuzzing an empty scenario set."""
        generator = FuzzScenarioGenerator()
        empty_set = ScenarioSet()

        fuzzed_set = generator.apply_fuzzing(empty_set)

        assert len(fuzzed_set.scenarios) == 0
        assert len(fuzzed_set.ground_truths) == 0

    def test_scenario_without_ground_truth(self):
        """Test handling scenario without matching ground truth."""
        scenario = GeneratedScenario(
            id="sc_orphan",
            name="Orphan scenario",
            gherkin="Scenario: Orphan",
            target_type=TargetType.TOOL,
            target_name="orphan_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_nonexistent",
        )

        scenario_set = ScenarioSet()
        scenario_set.add_scenario(scenario)

        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(scenario_set)

        # Should handle gracefully without crashing
        # No fuzz scenarios should be generated for orphan
        assert len(fuzzed_set.scenarios) == 1  # Just the original

    def test_ground_truth_without_schema(self):
        """Test handling ground truth without parameter schema."""
        ground_truth = GroundTruthSpec(
            id="gt_tool_no_params",
            target_type=TargetType.TOOL,
            target_name="no_params_tool",
            expected_behavior="Tool with no parameters",
            expected_output_schema={},  # Empty schema
            valid_input_examples=[],
            invalid_input_examples=[],
            semantic_reference="No params",
        )

        scenario = GeneratedScenario(
            id="sc_tool_no_params_happy_path_0",
            name="no_params_tool happy path",
            gherkin="Scenario: test",
            target_type=TargetType.TOOL,
            target_name="no_params_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_tool_no_params",
        )

        scenario_set = ScenarioSet()
        scenario_set.add_ground_truth(ground_truth)
        scenario_set.add_scenario(scenario)

        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(scenario_set)

        # Should handle gracefully - no parameters to fuzz
        assert len(fuzzed_set.scenarios) == 1  # Just the original


class TestFuzzGherkinGeneration:
    """Tests for Gherkin generation in fuzz scenarios."""

    def test_fuzz_scenario_has_valid_gherkin(self):
        """Test that generated fuzz scenarios have valid Gherkin structure."""
        ground_truth = GroundTruthSpec(
            id="gt_tool_example",
            target_type=TargetType.TOOL,
            target_name="example_tool",
            expected_behavior="Example tool",
            expected_output_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            valid_input_examples=[{"input": {"name": "test"}}],
            invalid_input_examples=[],
            semantic_reference="Example",
        )

        scenario = GeneratedScenario(
            id="sc_tool_example_happy_path_0",
            name="example happy path",
            gherkin="Scenario: example",
            target_type=TargetType.TOOL,
            target_name="example_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_tool_example",
        )

        scenario_set = ScenarioSet()
        scenario_set.add_ground_truth(ground_truth)
        scenario_set.add_scenario(scenario)

        generator = FuzzScenarioGenerator()
        fuzzed_set = generator.apply_fuzzing(scenario_set, max_fuzz_per_param=1)

        # Check fuzz scenarios have proper Gherkin
        for s in fuzzed_set.scenarios:
            if s.id != scenario.id:  # Fuzz scenario
                assert "Scenario:" in s.gherkin
                assert "Given" in s.gherkin
                assert "Then" in s.gherkin
                assert "Ground Truth ID:" in s.gherkin
