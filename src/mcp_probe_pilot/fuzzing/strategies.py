"""Fuzzing strategies for generating edge case and invalid input test values.

This module provides fuzzing strategy classes that analyze JSON schemas
and generate fuzz values to test server robustness against invalid inputs.

MVP Strategies:
- InvalidTypeStrategy: Type mismatch fuzzing (string where int expected, etc.)
- BoundaryValueStrategy: Boundary value testing (empty strings, MAX_INT, etc.)
- NullMissingStrategy: Null/missing parameter fuzzing
"""

import sys
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FuzzCategory(str, Enum):
    """Category of fuzz technique applied."""

    INVALID_TYPE = "invalid_type"
    BOUNDARY_VALUE = "boundary_value"
    NULL_MISSING = "null_missing"
    MALFORMED_JSON = "malformed_json"  # Future: not in MVP
    OVERFLOW = "overflow"  # Future: not in MVP


class FuzzValue(BaseModel):
    """A fuzzed value with metadata about the fuzzing technique.

    Attributes:
        value: The fuzzed value to use in testing.
        param_name: Name of the parameter being fuzzed.
        original_type: The expected type from the schema.
        fuzz_category: Category of the fuzzing technique.
        description: Human-readable description of the fuzz technique.
        expected_error: Whether a graceful error response is expected.
        expected_error_code: Expected JSON-RPC error code (e.g., -32602).
    """

    value: Any = Field(..., description="The fuzzed value")
    param_name: str = Field(..., description="Name of the parameter being fuzzed")
    original_type: str = Field(..., description="Expected type from schema")
    fuzz_category: FuzzCategory = Field(..., description="Category of fuzz technique")
    description: str = Field(..., description="Description of the fuzz technique")
    expected_error: bool = Field(
        default=True,
        description="Whether a graceful error response is expected",
    )
    expected_error_code: Optional[int] = Field(
        default=-32602,
        description="Expected JSON-RPC error code (Invalid params)",
    )


class BaseFuzzStrategy(ABC):
    """Abstract base class for fuzzing strategies.

    Subclasses implement specific fuzzing techniques by generating
    fuzz values based on parameter schemas.
    """

    @property
    @abstractmethod
    def category(self) -> FuzzCategory:
        """Get the fuzzing category for this strategy."""
        pass

    @abstractmethod
    def generate_fuzz_values(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate fuzz values for a parameter based on its schema.

        Args:
            param_name: Name of the parameter to fuzz.
            param_schema: JSON Schema definition for the parameter.

        Returns:
            List of FuzzValue objects representing fuzz test inputs.
        """
        pass

    def _get_schema_type(self, schema: dict[str, Any]) -> str:
        """Extract the type from a JSON schema.

        Args:
            schema: JSON Schema definition.

        Returns:
            The type string, or "any" if not specified.
        """
        schema_type = schema.get("type", "any")
        if isinstance(schema_type, list):
            # Handle union types - take the first non-null type
            for t in schema_type:
                if t != "null":
                    return t
            return "null"
        return schema_type


class InvalidTypeStrategy(BaseFuzzStrategy):
    """Fuzzing strategy that provides wrong data types for parameters.

    Generates values of incorrect types to test server type validation.
    For example, provides a string where an integer is expected.
    """

    @property
    def category(self) -> FuzzCategory:
        """Get the fuzzing category."""
        return FuzzCategory.INVALID_TYPE

    def generate_fuzz_values(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate type-mismatch fuzz values.

        Args:
            param_name: Name of the parameter to fuzz.
            param_schema: JSON Schema definition for the parameter.

        Returns:
            List of FuzzValue objects with wrong types.
        """
        schema_type = self._get_schema_type(param_schema)
        fuzz_values = []

        # Type mappings: for each expected type, provide wrong types
        type_mismatches: dict[str, list[tuple[Any, str]]] = {
            "string": [
                (12345, "integer instead of string"),
                (3.14159, "float instead of string"),
                (True, "boolean instead of string"),
                (["array", "value"], "array instead of string"),
                ({"key": "value"}, "object instead of string"),
            ],
            "integer": [
                ("not_a_number", "string instead of integer"),
                (3.14159, "float instead of integer"),
                (True, "boolean instead of integer"),
                (["array"], "array instead of integer"),
                ({"key": 1}, "object instead of integer"),
            ],
            "number": [
                ("not_a_number", "string instead of number"),
                (True, "boolean instead of number"),
                (["array"], "array instead of number"),
                ({"key": 1.5}, "object instead of number"),
            ],
            "boolean": [
                ("true", "string 'true' instead of boolean"),
                (1, "integer 1 instead of boolean"),
                (0, "integer 0 instead of boolean"),
                (["true"], "array instead of boolean"),
            ],
            "array": [
                ("not_an_array", "string instead of array"),
                (12345, "integer instead of array"),
                ({"key": "value"}, "object instead of array"),
                (True, "boolean instead of array"),
            ],
            "object": [
                ("not_an_object", "string instead of object"),
                (12345, "integer instead of object"),
                (["array"], "array instead of object"),
                (True, "boolean instead of object"),
            ],
        }

        mismatches = type_mismatches.get(schema_type, [])
        for wrong_value, description in mismatches:
            fuzz_values.append(
                FuzzValue(
                    value=wrong_value,
                    param_name=param_name,
                    original_type=schema_type,
                    fuzz_category=self.category,
                    description=f"Type mismatch: {description}",
                    expected_error=True,
                    expected_error_code=-32602,
                )
            )

        return fuzz_values


class BoundaryValueStrategy(BaseFuzzStrategy):
    """Fuzzing strategy that tests boundary values for parameters.

    Generates edge case values like empty strings, maximum integers,
    minimum integers, zero, and other boundary conditions.
    """

    # System-dependent max/min integers
    MAX_INT = sys.maxsize
    MIN_INT = -sys.maxsize - 1

    @property
    def category(self) -> FuzzCategory:
        """Get the fuzzing category."""
        return FuzzCategory.BOUNDARY_VALUE

    def generate_fuzz_values(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate boundary value fuzz values.

        Args:
            param_name: Name of the parameter to fuzz.
            param_schema: JSON Schema definition for the parameter.

        Returns:
            List of FuzzValue objects with boundary values.
        """
        schema_type = self._get_schema_type(param_schema)
        fuzz_values = []

        if schema_type == "string":
            fuzz_values.extend(self._string_boundaries(param_name, param_schema))
        elif schema_type in ("integer", "number"):
            fuzz_values.extend(self._numeric_boundaries(param_name, param_schema))
        elif schema_type == "array":
            fuzz_values.extend(self._array_boundaries(param_name, param_schema))
        elif schema_type == "object":
            fuzz_values.extend(self._object_boundaries(param_name, param_schema))

        return fuzz_values

    def _string_boundaries(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate boundary values for string parameters."""
        values = []
        original_type = "string"

        # Empty string
        values.append(
            FuzzValue(
                value="",
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: empty string",
                expected_error=True,
            )
        )

        # Whitespace only
        values.append(
            FuzzValue(
                value="   ",
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: whitespace-only string",
                expected_error=True,
            )
        )

        # Single character
        values.append(
            FuzzValue(
                value="a",
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: single character string",
                expected_error=False,  # May be valid
            )
        )

        # Check for minLength/maxLength constraints
        min_length = param_schema.get("minLength")
        max_length = param_schema.get("maxLength")

        if min_length is not None and min_length > 0:
            # String shorter than minimum
            short_string = "a" * (min_length - 1) if min_length > 1 else ""
            values.append(
                FuzzValue(
                    value=short_string,
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description=f"Boundary: string shorter than minLength ({min_length})",
                    expected_error=True,
                )
            )

        if max_length is not None:
            # String longer than maximum
            long_string = "a" * (max_length + 1)
            values.append(
                FuzzValue(
                    value=long_string,
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description=f"Boundary: string longer than maxLength ({max_length})",
                    expected_error=True,
                )
            )

        # Special characters
        values.append(
            FuzzValue(
                value="\x00\x01\x02",
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: null bytes and control characters",
                expected_error=True,
            )
        )

        return values

    def _numeric_boundaries(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate boundary values for numeric parameters."""
        values = []
        schema_type = self._get_schema_type(param_schema)
        original_type = schema_type

        # Zero
        values.append(
            FuzzValue(
                value=0,
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: zero",
                expected_error=False,  # May be valid
            )
        )

        # Negative one
        values.append(
            FuzzValue(
                value=-1,
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: negative one",
                expected_error=False,  # May be valid
            )
        )

        # Large positive integer
        values.append(
            FuzzValue(
                value=self.MAX_INT,
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: maximum integer",
                expected_error=True,
            )
        )

        # Large negative integer
        values.append(
            FuzzValue(
                value=self.MIN_INT,
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: minimum integer",
                expected_error=True,
            )
        )

        # Check for minimum/maximum constraints
        minimum = param_schema.get("minimum")
        maximum = param_schema.get("maximum")

        if minimum is not None:
            # Value below minimum
            values.append(
                FuzzValue(
                    value=minimum - 1,
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description=f"Boundary: below minimum ({minimum})",
                    expected_error=True,
                )
            )

        if maximum is not None:
            # Value above maximum
            values.append(
                FuzzValue(
                    value=maximum + 1,
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description=f"Boundary: above maximum ({maximum})",
                    expected_error=True,
                )
            )

        # For number type, also test float-specific values
        if schema_type == "number":
            values.extend([
                FuzzValue(
                    value=float("inf"),
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description="Boundary: positive infinity",
                    expected_error=True,
                ),
                FuzzValue(
                    value=float("-inf"),
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description="Boundary: negative infinity",
                    expected_error=True,
                ),
                FuzzValue(
                    value=float("nan"),
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description="Boundary: NaN",
                    expected_error=True,
                ),
            ])

        return values

    def _array_boundaries(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate boundary values for array parameters."""
        values = []
        original_type = "array"

        # Empty array
        values.append(
            FuzzValue(
                value=[],
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: empty array",
                expected_error=True,
            )
        )

        # Check for minItems/maxItems constraints
        min_items = param_schema.get("minItems")
        max_items = param_schema.get("maxItems")

        if min_items is not None and min_items > 0:
            # Array shorter than minimum
            short_array = ["item"] * (min_items - 1) if min_items > 1 else []
            values.append(
                FuzzValue(
                    value=short_array,
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description=f"Boundary: array shorter than minItems ({min_items})",
                    expected_error=True,
                )
            )

        if max_items is not None:
            # Array longer than maximum
            long_array = ["item"] * (max_items + 1)
            values.append(
                FuzzValue(
                    value=long_array,
                    param_name=param_name,
                    original_type=original_type,
                    fuzz_category=self.category,
                    description=f"Boundary: array longer than maxItems ({max_items})",
                    expected_error=True,
                )
            )

        return values

    def _object_boundaries(
        self,
        param_name: str,
        param_schema: dict[str, Any],
    ) -> list[FuzzValue]:
        """Generate boundary values for object parameters."""
        values = []
        original_type = "object"

        # Empty object
        values.append(
            FuzzValue(
                value={},
                param_name=param_name,
                original_type=original_type,
                fuzz_category=self.category,
                description="Boundary: empty object",
                expected_error=True,
            )
        )

        return values


class NullMissingStrategy(BaseFuzzStrategy):
    """Fuzzing strategy that tests null and missing parameter values.

    Generates null values and tests omission of required parameters
    to verify server handles missing data gracefully.
    """

    @property
    def category(self) -> FuzzCategory:
        """Get the fuzzing category."""
        return FuzzCategory.NULL_MISSING

    def generate_fuzz_values(
        self,
        param_name: str,
        param_schema: dict[str, Any],
        is_required: bool = True,
    ) -> list[FuzzValue]:
        """Generate null/missing fuzz values.

        Args:
            param_name: Name of the parameter to fuzz.
            param_schema: JSON Schema definition for the parameter.
            is_required: Whether this parameter is required.

        Returns:
            List of FuzzValue objects with null/missing values.
        """
        schema_type = self._get_schema_type(param_schema)
        fuzz_values = []

        # Explicit null value
        fuzz_values.append(
            FuzzValue(
                value=None,
                param_name=param_name,
                original_type=schema_type,
                fuzz_category=self.category,
                description="Null/Missing: explicit null value",
                expected_error=True,
                expected_error_code=-32602,
            )
        )

        # For required parameters, also test omission
        # (represented as a special marker)
        if is_required:
            fuzz_values.append(
                FuzzValue(
                    value=_OMIT_PARAM,
                    param_name=param_name,
                    original_type=schema_type,
                    fuzz_category=self.category,
                    description="Null/Missing: omit required parameter",
                    expected_error=True,
                    expected_error_code=-32602,
                )
            )

        # Type-specific empty values
        if schema_type == "string":
            pass  # Empty string covered by BoundaryValueStrategy
        elif schema_type == "array":
            pass  # Empty array covered by BoundaryValueStrategy
        elif schema_type == "object":
            pass  # Empty object covered by BoundaryValueStrategy

        return fuzz_values


# Sentinel object to represent parameter omission
class _OmitParameter:
    """Sentinel value indicating a parameter should be omitted."""

    def __repr__(self) -> str:
        return "<OMIT_PARAMETER>"


_OMIT_PARAM = _OmitParameter()


def is_omit_parameter(value: Any) -> bool:
    """Check if a value is the omit parameter sentinel.

    Args:
        value: The value to check.

    Returns:
        True if the value is the omit sentinel.
    """
    return isinstance(value, _OmitParameter)


# Default strategies for MVP
DEFAULT_STRATEGIES: list[BaseFuzzStrategy] = [
    InvalidTypeStrategy(),
    BoundaryValueStrategy(),
    NullMissingStrategy(),
]
