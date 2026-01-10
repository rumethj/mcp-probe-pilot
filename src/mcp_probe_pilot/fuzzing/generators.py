"""Fuzz scenario generator for creating fuzz test cases.

This module provides the FuzzScenarioGenerator class that applies fuzzing
strategies to existing test scenarios, generating fuzz variants with
appropriate ground truth for expected error responses.
"""

import json
import logging
from typing import Any, Optional

from ..generators.models import (
    FeatureFile,
    GeneratedScenario,
    GroundTruthSpec,
    ScenarioCategory,
    ScenarioSet,
    TargetType,
)
from .strategies import (
    BaseFuzzStrategy,
    BoundaryValueStrategy,
    DEFAULT_STRATEGIES,
    FuzzCategory,
    FuzzValue,
    InvalidTypeStrategy,
    NullMissingStrategy,
    is_omit_parameter,
)

logger = logging.getLogger(__name__)


# New category for fuzz scenarios
FUZZ_CATEGORY = ScenarioCategory.EDGE_CASE  # Fuzz scenarios are edge cases


class FuzzScenarioGenerator:
    """Generator that applies fuzzing strategies to create fuzz test scenarios.

    This generator takes a ScenarioSet with base scenarios and generates
    additional fuzz scenarios by applying fuzzing strategies to the input
    parameters of tools, resources, and prompts.

    Example:
        ```python
        # Create generator with default settings
        generator = FuzzScenarioGenerator()

        # Or configure which categories to fuzz
        generator = FuzzScenarioGenerator(
            categories=[ScenarioCategory.HAPPY_PATH, ScenarioCategory.EDGE_CASE]
        )

        # Apply fuzzing to existing scenarios
        fuzzed_set = generator.apply_fuzzing(scenario_set)
        print(f"Added {len(fuzzed_set.scenarios)} fuzz scenarios")
        ```

    Attributes:
        categories: Scenario categories to apply fuzzing to.
        strategies: List of fuzzing strategies to use.
    """

    # Default categories to fuzz
    DEFAULT_CATEGORIES = [ScenarioCategory.HAPPY_PATH, ScenarioCategory.EDGE_CASE]

    def __init__(
        self,
        categories: Optional[list[ScenarioCategory]] = None,
        strategies: Optional[list[BaseFuzzStrategy]] = None,
    ):
        """Initialize the fuzz scenario generator.

        Args:
            categories: Scenario categories to fuzz. Defaults to
                [HAPPY_PATH, EDGE_CASE].
            strategies: Fuzzing strategies to apply. Defaults to all MVP
                strategies (InvalidType, BoundaryValue, NullMissing).
        """
        self.categories = categories or self.DEFAULT_CATEGORIES
        self.strategies = strategies or DEFAULT_STRATEGIES

    def apply_fuzzing(
        self,
        scenario_set: ScenarioSet,
        max_fuzz_per_param: int = 3,
    ) -> ScenarioSet:
        """Apply fuzzing to scenarios and generate fuzz test cases.

        Takes the existing ScenarioSet and generates additional fuzz scenarios
        by applying fuzzing strategies to parameters. Fuzz scenarios and their
        ground truths are added to a new ScenarioSet.

        Args:
            scenario_set: The original ScenarioSet with base scenarios.
            max_fuzz_per_param: Maximum number of fuzz values per parameter
                per strategy (to limit explosion of test cases).

        Returns:
            A new ScenarioSet containing the original scenarios plus
            generated fuzz scenarios with their ground truths.
        """
        # Create a new ScenarioSet that includes everything from the original
        fuzzed_set = ScenarioSet(
            ground_truths=dict(scenario_set.ground_truths),
            scenarios=list(scenario_set.scenarios),
            features=list(scenario_set.features),
            workflow_ground_truths=dict(scenario_set.workflow_ground_truths),
            workflow_scenarios=list(scenario_set.workflow_scenarios),
        )

        # Track generated fuzz scenarios per target
        fuzz_counts: dict[str, int] = {}

        # Get scenarios to fuzz based on configured categories
        scenarios_to_fuzz = [
            s for s in scenario_set.scenarios if s.category in self.categories
        ]

        logger.info(
            f"Applying fuzzing to {len(scenarios_to_fuzz)} scenarios "
            f"(categories: {[c.value for c in self.categories]})"
        )

        for scenario in scenarios_to_fuzz:
            # Get the ground truth for this scenario
            ground_truth = scenario_set.get_ground_truth(scenario.ground_truth_id)
            if not ground_truth:
                logger.warning(
                    f"No ground truth found for scenario {scenario.id}, skipping"
                )
                continue

            # Generate fuzz scenarios for this base scenario
            fuzz_scenarios = self._generate_fuzz_scenarios_for_target(
                scenario,
                ground_truth,
                fuzz_counts,
                max_fuzz_per_param,
            )

            # Add fuzz scenarios and their ground truths to the set
            for fuzz_scenario, fuzz_ground_truth in fuzz_scenarios:
                fuzzed_set.add_ground_truth(fuzz_ground_truth)
                fuzzed_set.add_scenario(fuzz_scenario)

        logger.info(
            f"Generated {len(fuzzed_set.scenarios) - len(scenario_set.scenarios)} "
            f"fuzz scenarios"
        )

        return fuzzed_set

    def _generate_fuzz_scenarios_for_target(
        self,
        base_scenario: GeneratedScenario,
        ground_truth: GroundTruthSpec,
        fuzz_counts: dict[str, int],
        max_fuzz_per_param: int,
    ) -> list[tuple[GeneratedScenario, GroundTruthSpec]]:
        """Generate fuzz scenarios for a target based on its ground truth.

        Args:
            base_scenario: The base scenario to derive fuzz cases from.
            ground_truth: The ground truth containing schema information.
            fuzz_counts: Counter for generating unique IDs.
            max_fuzz_per_param: Max fuzz values per parameter per strategy.

        Returns:
            List of tuples containing (fuzz_scenario, fuzz_ground_truth).
        """
        results = []
        target_key = f"{base_scenario.target_type.value}_{base_scenario.target_name}"

        # Extract parameter schema from ground truth
        param_schema = self._extract_param_schema(ground_truth)
        if not param_schema:
            logger.debug(f"No parameters found for {target_key}, skipping fuzzing")
            return results

        properties = param_schema.get("properties", {})
        required = param_schema.get("required", [])

        # Apply each strategy to each parameter
        for param_name, param_def in properties.items():
            is_required = param_name in required

            for strategy in self.strategies:
                # Generate fuzz values for this parameter
                if isinstance(strategy, NullMissingStrategy):
                    fuzz_values = strategy.generate_fuzz_values(
                        param_name, param_def, is_required
                    )
                else:
                    fuzz_values = strategy.generate_fuzz_values(param_name, param_def)

                # Limit fuzz values per parameter
                fuzz_values = fuzz_values[:max_fuzz_per_param]

                for fuzz_value in fuzz_values:
                    # Generate unique ID
                    fuzz_counts[target_key] = fuzz_counts.get(target_key, 0) + 1
                    fuzz_index = fuzz_counts[target_key]

                    # Create fuzz scenario and ground truth
                    fuzz_scenario, fuzz_gt = self._create_fuzz_scenario(
                        base_scenario,
                        ground_truth,
                        fuzz_value,
                        fuzz_index,
                    )

                    results.append((fuzz_scenario, fuzz_gt))

        return results

    def _extract_param_schema(
        self,
        ground_truth: GroundTruthSpec,
    ) -> Optional[dict[str, Any]]:
        """Extract parameter schema from ground truth.

        The parameter schema is typically in expected_output_schema or
        can be inferred from valid_input_examples.

        Args:
            ground_truth: The ground truth specification.

        Returns:
            JSON Schema for the input parameters, or None if not found.
        """
        # Try to get from expected_output_schema (if it contains input schema)
        output_schema = ground_truth.expected_output_schema
        if output_schema and "properties" in output_schema:
            return output_schema

        # Try to infer from valid_input_examples
        if ground_truth.valid_input_examples:
            # Build a schema from the first example
            example = ground_truth.valid_input_examples[0]
            input_data = example.get("input", {})
            if input_data:
                return self._infer_schema_from_example(input_data)

        return None

    def _infer_schema_from_example(
        self,
        example: dict[str, Any],
    ) -> dict[str, Any]:
        """Infer a JSON schema from an example input.

        Args:
            example: An example input dictionary.

        Returns:
            Inferred JSON Schema.
        """
        properties = {}
        for key, value in example.items():
            properties[key] = self._infer_type_from_value(value)

        return {
            "type": "object",
            "properties": properties,
            "required": list(example.keys()),  # Assume all are required
        }

    def _infer_type_from_value(self, value: Any) -> dict[str, Any]:
        """Infer JSON schema type from a Python value.

        Args:
            value: A Python value.

        Returns:
            JSON Schema type definition.
        """
        if value is None:
            return {"type": "null"}
        elif isinstance(value, bool):
            return {"type": "boolean"}
        elif isinstance(value, int):
            return {"type": "integer"}
        elif isinstance(value, float):
            return {"type": "number"}
        elif isinstance(value, str):
            return {"type": "string"}
        elif isinstance(value, list):
            return {"type": "array"}
        elif isinstance(value, dict):
            return {"type": "object"}
        else:
            return {"type": "any"}

    def _create_fuzz_scenario(
        self,
        base_scenario: GeneratedScenario,
        base_ground_truth: GroundTruthSpec,
        fuzz_value: FuzzValue,
        fuzz_index: int,
    ) -> tuple[GeneratedScenario, GroundTruthSpec]:
        """Create a fuzz scenario from a base scenario and fuzz value.

        Args:
            base_scenario: The original scenario to base the fuzz on.
            base_ground_truth: The original ground truth.
            fuzz_value: The fuzz value to apply.
            fuzz_index: Index for unique ID generation.

        Returns:
            Tuple of (fuzz_scenario, fuzz_ground_truth).
        """
        # Generate IDs
        fuzz_scenario_id = f"{base_scenario.id}_fuzz_{fuzz_index}"
        fuzz_gt_id = f"{base_ground_truth.id}_fuzz_{fuzz_index}"

        # Create fuzz ground truth (expects error)
        fuzz_ground_truth = GroundTruthSpec(
            id=fuzz_gt_id,
            target_type=base_ground_truth.target_type,
            target_name=base_ground_truth.target_name,
            expected_behavior=(
                f"Server should gracefully handle invalid input: {fuzz_value.description}. "
                f"Expected to return JSON-RPC error code {fuzz_value.expected_error_code} "
                f"with appropriate error message."
            ),
            expected_output_schema={
                "type": "object",
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "integer"},
                            "message": {"type": "string"},
                        },
                        "required": ["code", "message"],
                    }
                },
            },
            valid_input_examples=[],
            invalid_input_examples=[
                {
                    "input": {fuzz_value.param_name: fuzz_value.value}
                    if not is_omit_parameter(fuzz_value.value)
                    else {"_omitted": fuzz_value.param_name},
                    "expected_error": f"JSON-RPC error code {fuzz_value.expected_error_code}",
                }
            ],
            semantic_reference=(
                f"Graceful error handling for {fuzz_value.fuzz_category.value} input: "
                f"{fuzz_value.description}"
            ),
        )

        # Build fuzz Gherkin scenario
        fuzz_gherkin = self._build_fuzz_gherkin(
            base_scenario,
            fuzz_value,
            fuzz_gt_id,
        )

        # Create fuzz scenario
        fuzz_scenario = GeneratedScenario(
            id=fuzz_scenario_id,
            name=f"{base_scenario.target_name} fuzz - {fuzz_value.description}",
            gherkin=fuzz_gherkin,
            target_type=base_scenario.target_type,
            target_name=base_scenario.target_name,
            category=FUZZ_CATEGORY,
            ground_truth_id=fuzz_gt_id,
            description=(
                f"Fuzz test: {fuzz_value.description} for parameter "
                f"'{fuzz_value.param_name}' (expected type: {fuzz_value.original_type})"
            ),
        )

        return fuzz_scenario, fuzz_ground_truth

    def _build_fuzz_gherkin(
        self,
        base_scenario: GeneratedScenario,
        fuzz_value: FuzzValue,
        ground_truth_id: str,
    ) -> str:
        """Build Gherkin text for a fuzz scenario.

        Args:
            base_scenario: The base scenario.
            fuzz_value: The fuzz value being tested.
            ground_truth_id: The ground truth ID for reference.

        Returns:
            Gherkin text for the fuzz scenario.
        """
        target_type = base_scenario.target_type
        target_name = base_scenario.target_name

        # Format the fuzz value for display in Gherkin
        if is_omit_parameter(fuzz_value.value):
            fuzz_args = f'{{"_omit_param": "{fuzz_value.param_name}"}}'
            when_clause = (
                f'When I call {target_type.value} "{target_name}" '
                f'without the required parameter "{fuzz_value.param_name}"'
            )
        else:
            try:
                value_json = json.dumps(fuzz_value.value)
            except (TypeError, ValueError):
                value_json = repr(fuzz_value.value)
            fuzz_args = f'{{"{fuzz_value.param_name}": {value_json}}}'
            when_clause = (
                f'When I call {target_type.value} "{target_name}" '
                f"with fuzz arguments {fuzz_args}"
            )

        gherkin = f"""Scenario: {target_name} fuzz - {fuzz_value.description}
  # Fuzz Category: {fuzz_value.fuzz_category.value}
  # Ground Truth ID: {ground_truth_id}
  Given the MCP server is running
  {when_clause}
  Then the server should return a graceful error
  And the error code should be {fuzz_value.expected_error_code or "a valid JSON-RPC error code"}
  And the response should match fuzz ground truth "{ground_truth_id}\""""

        return gherkin

    def get_fuzz_statistics(
        self,
        original_set: ScenarioSet,
        fuzzed_set: ScenarioSet,
    ) -> dict[str, Any]:
        """Get statistics about the fuzzing operation.

        Args:
            original_set: The original ScenarioSet before fuzzing.
            fuzzed_set: The ScenarioSet after fuzzing.

        Returns:
            Dictionary with fuzzing statistics.
        """
        original_count = len(original_set.scenarios)
        fuzzed_count = len(fuzzed_set.scenarios)
        new_scenarios = fuzzed_count - original_count

        # Count by fuzz category
        category_counts: dict[str, int] = {}
        for scenario in fuzzed_set.scenarios:
            if scenario.id not in [s.id for s in original_set.scenarios]:
                # This is a fuzz scenario
                if scenario.description:
                    for cat in FuzzCategory:
                        if cat.value in scenario.description:
                            category_counts[cat.value] = (
                                category_counts.get(cat.value, 0) + 1
                            )
                            break

        return {
            "original_scenarios": original_count,
            "fuzzed_scenarios": fuzzed_count,
            "new_fuzz_scenarios": new_scenarios,
            "fuzz_by_category": category_counts,
            "strategies_used": [type(s).__name__ for s in self.strategies],
            "categories_fuzzed": [c.value for c in self.categories],
        }
