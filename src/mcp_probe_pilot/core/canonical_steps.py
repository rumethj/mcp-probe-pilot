"""Single source of truth for the canonical Gherkin step vocabulary.

Every step that the generator may produce and the validator accepts is
defined exactly once in ``_CANONICAL_STEPS``.  Two derived views are
exported:

* ``CANONICAL_PATTERNS`` – flat ``(keyword, text)`` pairs consumed by
  :class:`~mcp_probe_pilot.validate.validator.CanonicalStepRegistry`.
* ``render_step_library_prompt()`` – markdown prompt fragment appended
  to every LLM generation request.
"""

from __future__ import annotations

from string import Template

# ------------------------------------------------------------------
# Master step list – (keyword, section_tag, step_text)
#
# *section_tag* controls how the step is grouped in the LLM prompt.
# The list order determines the order of CANONICAL_PATTERNS (which
# the validator iterates for first-match).
# ------------------------------------------------------------------

_CANONICAL_STEPS: list[tuple[str, str, str]] = [
    # Setup
    ("given", "setup", 'the MCP Client is initialized and connected to the MCP Server: "{server_command}"'),
    # Direct actions
    ("when", "action", 'the MCP Client calls the tool "{tool_name}" with parameters'),
    ("when", "action", 'the MCP Client calls the tool "{tool_name}"'),
    ("when", "action", 'the MCP Client reads the resource "{resource_uri}"'),
    ("when", "action", 'the MCP Client gets the prompt "{prompt_name}" with arguments'),
    ("when", "action", 'the MCP Client gets the prompt "{prompt_name}"'),
    # Saved-context actions
    ("when", "saved_action", 'the MCP Client calls the tool "{tool_name}" with saved parameters'),
    ("when", "saved_action", 'the MCP Client reads the resource with URI from saved "{variable}"'),
    ("when", "saved_action", 'the MCP Client gets the prompt "{prompt_name}" with saved arguments'),
    # Context variable
    ("then", "context", 'I save the response field "{field}" as "{variable}"'),
    ("then", "context", 'I save the full response as "{variable}"'),
    ("then", "context", 'I construct the value "{template}" and save as "{variable}"'),
    # Response assertions
    ("then", "assertion", "the response should be successful"),
    ("then", "assertion", "the response should be a failure"),
    ("then", "assertion", 'the response should contain "{key}" with value "{value}"'),
    ("then", "assertion", 'the response should contain "{key}" with value {value:d}'),
    ("then", "assertion", 'the response should contain "{key}"'),
    ("then", "assertion", 'the response key "{key}" should equal saved variable "{variable}"'),
    ("then", "assertion", 'the response field "{field}" should be "{expected_value}"'),
    ("then", "assertion", 'the response field "{field}" should be {expected_value:d}'),
    ("then", "assertion", 'the response field "{field}" should be null'),
    ("then", "assertion", 'the response field "{field}" should be []'),
    ("then", "assertion", 'the response field "{field}" should be {json_list}'),
    ("then", "assertion", 'the response content type should be "{content_type}"'),
    ("then", "assertion", "the response should contain an error"),
    ("then", "assertion", 'the error message should indicate "{expected_message}"'),
    ("then", "assertion", "the response should contain prompt messages"),
    # Elicitation (client-side)
    ("given", "elicitation", "the next elicitation response will accept with"),
    ("given", "elicitation", "the next elicitation response will decline"),
    ("given", "elicitation", "the next elicitation response will cancel"),
    ("then", "elicitation", "an elicitation request should have been received"),
    ("then", "elicitation", 'the elicitation message should contain "{text}"'),
    # Sampling (client-side)
    ("then", "sampling", "a sampling request should have been received"),
    # Roots (client-side)
    ("given", "roots", "the MCP Client has roots"),
    ("when", "roots", "the MCP Client sends roots list changed notification"),
    ("then", "roots", "a roots list request should have been received"),
]

# ------------------------------------------------------------------
# Flat (keyword, text) pairs – backward-compatible with
# CanonicalStepRegistry which expects list[tuple[str, str]].
# ------------------------------------------------------------------

CANONICAL_PATTERNS: list[tuple[str, str]] = [
    (kw, text) for kw, _, text in _CANONICAL_STEPS
]

# ------------------------------------------------------------------
# Prompt rendering
# ------------------------------------------------------------------

_KEYWORD_PREFIX: dict[str, str] = {
    "given": "Given",
    "when": "When",
    "then": "Then",
}

_PROMPT_TEMPLATE = Template("""\
## Canonical Step Patterns (USE THESE EXACTLY - do not create variations)

### Setup Steps (Given)
$setup_steps

### Action Steps (When)
$action_steps

### Action Steps with Saved Context (When) -- for integration/chaining scenarios
$saved_action_steps

### Response Assertion Steps (Then/And)
$assertion_steps

### Context Variable Steps (Then/And) -- for chaining MCP calls
$context_steps

### Elicitation Steps (Given/Then) -- for servers that request user input via elicitation
$elicitation_steps

### Sampling Steps (Then) -- for servers that request LLM completions via sampling
$sampling_steps

### Roots Steps (Given/When/Then) -- for servers that query client filesystem roots
$roots_steps
""")

_SECTION_ORDER = [
    "setup", "action", "saved_action", "assertion", "context",
    "elicitation", "sampling", "roots",
]

_SECTION_TEMPLATE_VAR: dict[str, str] = {
    "setup": "setup_steps",
    "action": "action_steps",
    "saved_action": "saved_action_steps",
    "assertion": "assertion_steps",
    "context": "context_steps",
    "elicitation": "elicitation_steps",
    "sampling": "sampling_steps",
    "roots": "roots_steps",
}


def render_step_library_prompt() -> str:
    """Build the canonical step library as a markdown prompt fragment."""
    groups: dict[str, list[str]] = {}
    for kw, section, text in _CANONICAL_STEPS:
        prefix = _KEYWORD_PREFIX[kw]
        groups.setdefault(section, []).append(f"- {prefix} {text}")

    return _PROMPT_TEMPLATE.substitute(
        **{
            _SECTION_TEMPLATE_VAR[sec]: "\n".join(groups.get(sec, []))
            for sec in _SECTION_ORDER
        }
    )
