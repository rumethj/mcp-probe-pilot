# Plan

Uses an LLM with structured output to generate test scenario plans from MCP discovery results.

## Purpose

The planner sits between discovery and generation. Given the discovered tools, resources, and prompts, it asks the LLM to produce BDD scenario titles for each primitive (unit tests) and cross-primitive workflows (integration tests).

## Key Concepts

- **Structured Output** – The LLM is invoked via LangChain's `with_structured_output(schema)` method, ensuring the response is parsed into a Pydantic model (`_ScenarioListOutput` for unit tests, `IntegrationTestPlanResult` for integration tests) rather than free-form text.
- **Per-Primitive Planning** – Each tool, resource, and prompt gets its own LLM call with contextual metadata (name, description, input schema, mime type, arguments). This produces focused, relevant scenario titles.
- **Integration Planning** – A single LLM call receives a summary of all discovered primitives and generates cross-primitive workflow scenarios with pattern tags (e.g. "prompt-driven", "chain-of-calls").
- **Summary Helpers** – Static methods (`_summarise_tools`, `_summarise_resources`, `_summarise_prompts`) format discovery results into human-readable text for the LLM prompt. These handle edge cases like missing descriptions and empty primitive lists.

## Modules

| File | Description |
|------|-------------|
| `planner.py` | `Planner` – LLM-backed scenario title generator. |
| `prompts.py` | Prompt templates for unit and integration test planning. |
