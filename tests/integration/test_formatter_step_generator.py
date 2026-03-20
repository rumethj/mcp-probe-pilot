"""Integration tests: GherkinFormatter -> StepImplementationGenerator.

Verifies that a GherkinFeatureCollection with prebuilt and novel steps
is handled correctly by the step generator.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_probe_pilot.core.models.gherkin_feature import (
    DataTable,
    GherkinFeature,
    GherkinFeatureCollection,
    GherkinScenario,
    GherkinStep,
    GherkinStepType,
)
from mcp_probe_pilot.generate.step_implementation_generator import (
    StepImplementationGenerator,
    StepImplementationResult,
)


# ------------------------------------------------------------------
# Prebuilt steps code
# ------------------------------------------------------------------

PREBUILT_STEPS = """\
from behave import given, when, then

@given('the MCP Client is initialized and connected to the MCP Server: "{server_command}"')
def step_connected(context, server_command):
    pass

@when('the MCP Client calls the tool "{tool_name}" with parameters')
def step_call_tool(context, tool_name):
    pass

@then('the response should be successful')
def step_response_success(context):
    pass
"""


# ------------------------------------------------------------------
# Steps with prebuilt implementations are skipped
# ------------------------------------------------------------------


class TestPrebuiltStepsSkipped:
    @pytest.mark.asyncio
    async def test_prebuilt_steps_are_skipped(self, tmp_path: Path) -> None:
        """A GherkinFeatureCollection with steps that already have prebuilt
        implementations results in those steps being skipped."""

        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="Test Feature",
                scenarios=[
                    GherkinScenario(
                        name="All prebuilt",
                        steps=[
                            GherkinStep(
                                text='the MCP Client is initialized and connected to the MCP Server: "test"',
                                step_type=GherkinStepType.GIVEN,
                            ),
                            GherkinStep(
                                text='the MCP Client calls the tool "search" with parameters',
                                step_type=GherkinStepType.WHEN,
                                data_table=DataTable(
                                    headers=["parameter", "value"],
                                    rows=[["query", "test"]],
                                ),
                            ),
                            GherkinStep(
                                text="the response should be successful",
                                step_type=GherkinStepType.THEN,
                            ),
                        ],
                    ),
                ],
            ),
        ])

        llm = MagicMock()
        llm.ainvoke = AsyncMock()

        generator = StepImplementationGenerator(
            llm=llm,
            prebuilt_steps_code=PREBUILT_STEPS,
            output_dir=tmp_path,
        )
        result = await generator.generate_all(collection)

        assert isinstance(result, StepImplementationResult)
        assert result.steps_generated == 0
        assert result.steps_skipped == 3
        llm.ainvoke.assert_not_called()


# ------------------------------------------------------------------
# Novel steps produce valid output
# ------------------------------------------------------------------


GENERATED_CODE = """\
```python
from behave import then

@then('the response should contain an error')
def step_error(context):
    assert context.response.get("error") is not None
# EOF
```
"""


class TestNovelStepsGenerated:
    @pytest.mark.asyncio
    async def test_novel_steps_produce_valid_output(self, tmp_path: Path) -> None:
        """A collection with novel steps produces a StepImplementationResult
        with correct steps_generated count and a syntactically valid Python
        output file."""

        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="Test Feature",
                scenarios=[
                    GherkinScenario(
                        name="Error scenario",
                        steps=[
                            GherkinStep(
                                text='the MCP Client is initialized and connected to the MCP Server: "test"',
                                step_type=GherkinStepType.GIVEN,
                            ),
                            GherkinStep(
                                text="the response should contain an error",
                                step_type=GherkinStepType.THEN,
                            ),
                        ],
                    ),
                ],
            ),
        ])

        response = MagicMock()
        response.content = GENERATED_CODE
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=response)

        generator = StepImplementationGenerator(
            llm=llm,
            prebuilt_steps_code=PREBUILT_STEPS,
            output_dir=tmp_path,
        )
        result = await generator.generate_all(collection)

        assert result.steps_generated >= 1

        steps_file = tmp_path / "steps" / "steps.py"
        assert steps_file.exists()

        import ast
        code = steps_file.read_text(encoding="utf-8")
        ast.parse(code)
