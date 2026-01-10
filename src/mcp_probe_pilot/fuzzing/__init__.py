"""Fuzzing module for generating edge case and invalid input test scenarios.

This module provides fuzzing strategies and a generator for creating fuzz
test scenarios from base scenarios. It supports:

- Invalid type injection: Provide wrong data types for parameters
- Boundary value testing: Test limits of acceptable values
- Null/missing value fuzzing: Omit required parameters or pass null

Example:
    ```python
    from mcp_probe_pilot.fuzzing import FuzzScenarioGenerator, ScenarioCategory

    # Create generator with default settings (fuzz happy_path and edge_case)
    generator = FuzzScenarioGenerator()

    # Or configure specific categories to fuzz
    generator = FuzzScenarioGenerator(
        categories=[ScenarioCategory.HAPPY_PATH]
    )

    # Apply fuzzing to existing scenarios
    fuzzed_set = generator.apply_fuzzing(scenario_set)
    ```
"""

from .generators import FuzzScenarioGenerator
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

__all__ = [
    # Generator
    "FuzzScenarioGenerator",
    # Strategies
    "BaseFuzzStrategy",
    "InvalidTypeStrategy",
    "BoundaryValueStrategy",
    "NullMissingStrategy",
    "DEFAULT_STRATEGIES",
    # Models
    "FuzzCategory",
    "FuzzValue",
    # Utilities
    "is_omit_parameter",
]
