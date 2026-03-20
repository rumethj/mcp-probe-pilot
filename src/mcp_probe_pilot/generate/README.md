# Generate

Produces Gherkin `.feature` files and Python step implementations from test plans via LLM.

## Purpose

This module is the largest stage of the pipeline. It takes `UnitTestPlanResult` and `IntegrationTestPlanResult` from the planner and produces:
1. Validated `.feature` files on disk
2. A `steps/steps.py` file containing all step definitions (prebuilt + LLM-generated)

## Key Concepts

- **GherkinFeatureGenerator** – Sends structured prompts to the LLM (system + human messages), extracts Gherkin from the markdown response, validates it with the official `gherkin-official` parser, and writes `.feature` files. Supports batching (splitting scenarios into groups of `MAX_SCENARIOS_PER_BATCH`) and merging the results into a single feature file.
- **Step Reuse Tracking** – As features are generated sequentially, step patterns extracted from earlier features are appended to subsequent prompts to encourage the LLM to reuse existing step patterns rather than inventing new ones.
- **GherkinFormatter** – Parses `.feature` files into `GherkinFeatureCollection`, applies text normalization rules to reduce step variation (e.g. "the response contains" → "the response should contain"), and writes normalised files back to disk.
- **StepImplementationGenerator** – For each scenario, identifies which steps are already implemented (via AST-based pattern extraction from the prebuilt `steps.py`), sends only the missing steps to the LLM, and appends the generated code. Includes AST-based duplicate filtering and final validation.
- **Pattern Matching** – Step pattern comparison is case-insensitive with flexible placeholder matching (`{name}` matches `{number}`, `{json_value}`, etc.) to avoid false "missing step" reports.

## Modules

| File | Description |
|------|-------------|
| `gherkin_feature_generator.py` | `GherkinFeatureGenerator` – LLM-driven `.feature` file generation. |
| `gherkin_formatter.py` | `GherkinFormatter`, `GherkinParser`, `StepNormalizer` – parsing and normalisation. |
| `step_implementation_generator.py` | `StepImplementationGenerator` – LLM-driven step definition generation. |
| `prompts.py` | Prompt templates for all generation stages. |
