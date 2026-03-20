"""Unit tests for the StepImplementationGenerator and module-level utilities."""

from __future__ import annotations

import pytest

from mcp_probe_pilot.generate.step_implementation_generator import (
    StepImplementationGenerator,
    _extract_pattern_from_decorator,
    _merge_pattern_dicts,
    _to_generic_pattern,
    extract_implemented_steps,
    normalize_step_to_pattern,
    patterns_match,
)


# ------------------------------------------------------------------
# normalize_step_to_pattern
# ------------------------------------------------------------------


class TestNormalizeStepToPattern:
    def test_quoted_strings(self) -> None:
        result = normalize_step_to_pattern('the response should contain "task_id"')
        assert result == 'the response should contain "{placeholder}"'

    def test_numbers(self) -> None:
        result = normalize_step_to_pattern('the response field "count" should be 42')
        assert '"{placeholder}"' in result
        assert "{number}" in result

    def test_json_array(self) -> None:
        result = normalize_step_to_pattern('the response field "tags" should be ["a", "b"]')
        assert "{json_value}" in result

    def test_behave_type_converter(self) -> None:
        result = normalize_step_to_pattern("value {expected:int}")
        assert result == "value {number}"

    def test_plain_placeholder(self) -> None:
        result = normalize_step_to_pattern("has field {field}")
        assert result == "has field {placeholder}"


# ------------------------------------------------------------------
# patterns_match
# ------------------------------------------------------------------


class TestPatternsMatch:
    def test_exact_match(self) -> None:
        assert patterns_match("the response should be successful", "the response should be successful")

    def test_case_insensitive(self) -> None:
        assert patterns_match("The Response", "the response")

    def test_number_vs_placeholder(self) -> None:
        assert patterns_match("value {placeholder}", "value {number}")

    def test_json_value_vs_placeholder(self) -> None:
        assert patterns_match("field {json_value}", "field {placeholder}")

    def test_quoted_vs_unquoted_placeholder(self) -> None:
        assert patterns_match('"{placeholder}"', "{placeholder}")

    def test_no_match(self) -> None:
        assert not patterns_match("foo bar", "baz qux")


# ------------------------------------------------------------------
# _to_generic_pattern
# ------------------------------------------------------------------


class TestToGenericPattern:
    def test_number_to_placeholder(self) -> None:
        assert _to_generic_pattern("value {number}") == "value {placeholder}"

    def test_json_value_to_placeholder(self) -> None:
        assert _to_generic_pattern("field {json_value}") == "field {placeholder}"

    def test_quoted_placeholder_unquoted(self) -> None:
        assert _to_generic_pattern('"{placeholder}"') == "{placeholder}"


# ------------------------------------------------------------------
# extract_implemented_steps
# ------------------------------------------------------------------


class TestExtractImplementedSteps:
    def test_extracts_given_when_then(self) -> None:
        code = """
from behave import given, when, then

@given('the client is connected')
def step_given(context):
    pass

@when('the client calls "{tool}"')
def step_when(context, tool):
    pass

@then('the response should be successful')
def step_then(context):
    pass
"""
        steps = extract_implemented_steps(code)
        assert "the client is connected" in steps
        assert 'the client calls "{tool}"' in steps
        assert "the response should be successful" in steps
        assert "given" in steps["the client is connected"]
        assert "when" in steps['the client calls "{tool}"']

    def test_handles_syntax_error(self) -> None:
        result = extract_implemented_steps("def broken(")
        assert result == {}

    def test_multi_decorator(self) -> None:
        code = """
from behave import given, when

@given('the setup')
@when('the setup')
def step_impl(context):
    pass
"""
        steps = extract_implemented_steps(code)
        assert "given" in steps["the setup"]
        assert "when" in steps["the setup"]


# ------------------------------------------------------------------
# _merge_pattern_dicts
# ------------------------------------------------------------------


class TestMergePatternDicts:
    def test_merge_new(self) -> None:
        target = {"a": {"given"}}
        source = {"b": {"when"}}
        _merge_pattern_dicts(target, source)
        assert "b" in target
        assert target["b"] == {"when"}

    def test_merge_existing(self) -> None:
        target = {"a": {"given"}}
        source = {"a": {"when"}}
        _merge_pattern_dicts(target, source)
        assert target["a"] == {"given", "when"}


# ------------------------------------------------------------------
# StepImplementationGenerator._extract_python_code
# ------------------------------------------------------------------


class TestExtractPythonCode:
    def test_extracts_from_python_block(self) -> None:
        response = "Here is the code:\n```python\nprint('hello')\n# EOF\n```\nDone."
        result = StepImplementationGenerator._extract_python_code(response)
        assert "print('hello')" in result
        assert "# EOF" not in result

    def test_extracts_from_plain_block(self) -> None:
        response = "Code:\n```\nprint('world')\n```"
        result = StepImplementationGenerator._extract_python_code(response)
        assert "print('world')" in result

    def test_raises_on_no_code_block(self) -> None:
        from mcp_probe_pilot.generate.step_implementation_generator import StepImplementationError
        with pytest.raises(StepImplementationError):
            StepImplementationGenerator._extract_python_code("No code here.")
