# Test Scenario Generator (GherkinFeatureGenerator) — Internal Flowchart

## Overview

The Test Scenario Generator expands scenario titles from the Planner into complete, executable Gherkin `.feature` files. It uses LLM-driven synthesis constrained by the Canonical Step Library, with code context retrieved from ChromaDB.

## Main Orchestration Flow

```mermaid
flowchart TD
    Start([Start: generate_all]) --> MkDir["Create output_dir\nif not exists"]
    MkDir --> InitResult["Initialize GenerationResult\n(files_generated=0, files_failed=0)"]
    InitResult --> BuildQueue["Build generation_queue:\nlist of (prim_type, prim_name, scenarios)"]

    BuildQueue --> QueueTools["For each discovered tool:\nget scenario plans from UnitTestPlanResult\n→ append ('tool', name, scenarios)"]
    QueueTools --> QueueRes["For each discovered resource:\nget scenario plans\n→ append ('resource', identifier, scenarios)"]
    QueueRes --> QueuePrompts["For each discovered prompt:\nget scenario plans\n→ append ('prompt', name, scenarios)"]

    QueuePrompts --> SeqLoop["Process queue SEQUENTIALLY\n(enables step reuse tracking)"]
    SeqLoop --> ProgressStart["on_progress('start', prim_type, prim_name)"]
    ProgressStart --> GenUnit["_generate_unit_feature(\nprim_type, prim_name, scenarios)"]
    GenUnit --> GenSuccess{Success?}
    GenSuccess -- Yes --> IncGen["files_generated += 1\non_progress('done')"]
    GenSuccess -- No --> IncFail["files_failed += 1\non_progress('failed')"]
    IncGen --> MoreQueue{More in queue?}
    IncFail --> MoreQueue
    MoreQueue -- Yes --> SeqLoop
    MoreQueue -- No --> CheckInteg{Integration\nscenarios exist?}

    CheckInteg -- Yes --> GenInteg["_generate_integration_feature(\nintegration_plan)"]
    GenInteg --> IntegSuccess{Success?}
    IntegSuccess -- Yes --> IncGenI["files_generated += 1"]
    IntegSuccess -- No --> IncFailI["files_failed += 1"]
    IncGenI --> EndGen
    IncFailI --> EndGen
    CheckInteg -- No --> EndGen
    EndGen([Output: GenerationResult\n— files_generated, files_failed,\nvalidation_warnings])

    style Start fill:#e8f5e9
    style EndGen fill:#e8f5e9
```

## Unit Feature Generation Flow

```mermaid
flowchart TD
    Start([_generate_unit_feature]) --> Semaphore["Acquire semaphore\n(concurrency limit = 3)"]
    Semaphore --> QueryCtx["_query_code_context(prim_name)\n— 3 ChromaDB queries:\n1. primitive name\n2. name + 'seed data fixtures'\n3. name + 'validation error handling'"]
    QueryCtx --> DedupeResults["Deduplicate results by entity name\nFormat as markdown code blocks"]

    DedupeResults --> BatchCheck{"len(scenarios) >\nMAX_SCENARIOS_PER_BATCH\n(15)?"}
    BatchCheck -- Yes --> SplitBatches["Split into batches of 15"]
    BatchCheck -- No --> SingleBatch["Single batch"]

    SplitBatches --> BatchLoop["For each batch"]
    SingleBatch --> BatchLoop

    BatchLoop --> RenderPrompt["_render_unit_prompt()"]
    RenderPrompt --> PromptType{prim_type?}

    PromptType -- tool --> RenderTool["Render TOOL_UNIT_HUMAN:\n• tool_name, description\n• input_schema (JSON)\n• schema_hints (enum/default/pattern)\n• scenarios list\n• code_context"]
    PromptType -- resource --> RenderRes["Render RESOURCE_UNIT_HUMAN:\n• resource_uri, name, description\n• mime_type, is_template\n• scenarios list\n• code_context"]
    PromptType -- prompt --> RenderPr["Render PROMPT_UNIT_HUMAN:\n• prompt_name, description\n• arguments (name, required/optional)\n• scenarios list\n• code_context"]

    RenderTool --> AppendStepLib
    RenderRes --> AppendStepLib
    RenderPr --> AppendStepLib

    AppendStepLib["_append_step_reuse_context():\n1. Append CANONICAL_STEP_LIBRARY\n2. Append 'Already Used Steps'\n   (from previous features)"]
    AppendStepLib --> GenValidate["_generate_and_validate(\nhuman_content, label)"]
    GenValidate --> MoreBatches{More batches?}
    MoreBatches -- Yes --> BatchLoop
    MoreBatches -- No --> MergeCheck{Multiple\nbatches?}

    MergeCheck -- Yes --> MergeBatches["_merge_feature_batches():\nKeep Feature header + Background\nfrom first batch, append Scenario\nblocks from subsequent batches"]
    MergeCheck -- No --> UseSingle["Use single batch output"]

    MergeBatches --> ExtractSteps
    UseSingle --> ExtractSteps

    ExtractSteps["_extract_steps_from_gherkin():\nRegex-extract step texts\n(Given/When/Then/And/But lines)\nAdd to _generated_step_patterns set"]
    ExtractSteps --> WriteFile["Write .feature file:\n{prim_type}_{safe_name}.feature"]
    WriteFile --> EndUnit([Output: file path + optional warning])

    style Start fill:#e8f5e9
    style EndUnit fill:#e8f5e9
```

## LLM Generation and Validation Flow

```mermaid
flowchart TD
    Start([_generate_and_validate]) --> InitRetry["attempt = 0\nMAX_RETRIES = 1"]
    InitRetry --> CallLLM["_call_llm(human_content):\n1. Render SYSTEM_PROMPT with server_command\n2. Build [SystemMessage, HumanMessage]\n3. llm.ainvoke(messages)\n4. Return raw response text"]
    CallLLM --> ProcessOutput["_process_llm_output(raw_response, label)"]

    ProcessOutput --> ExtractGherkin["_extract_gherkin(raw_response)"]
    ExtractGherkin --> TryCodeBlock{"Contains\n```gherkin\\n...``` ?"}
    TryCodeBlock -- Yes --> ExtractFromGherkinBlock["Extract content from\ngherkin code block"]
    TryCodeBlock -- No --> TryGenericBlock{"Contains\n```\\n...``` ?"}
    TryGenericBlock -- Yes --> ExtractFromGenericBlock["Extract content from\ngeneric code block"]
    TryGenericBlock -- No --> TryRawGherkin{"Starts with\nFeature: or @?"}
    TryRawGherkin -- Yes --> UseRawContent["Use cleaned content directly"]
    TryRawGherkin -- No --> NoGherkin([GherkinGenerationError:\nNo Gherkin content found])

    ExtractFromGherkinBlock --> CheckEndMarker
    ExtractFromGenericBlock --> CheckEndMarker
    UseRawContent --> CheckEndMarker

    CheckEndMarker{"[END_OF_FEATURE]\nmarker present?"}
    CheckEndMarker -- No --> TrimLast["_remove_last_scenario():\nDrop final Scenario block\n(assumed incomplete)\n+ Set warning"]
    CheckEndMarker -- Yes --> ValidateSyntax

    TrimLast --> ValidateSyntax["_validate_gherkin():\nParse with gherkin-official\nParser()"]
    ValidateSyntax --> SyntaxOk{Valid syntax?}
    SyntaxOk -- No --> RetryCheck{attempt <\nMAX_RETRIES?}
    RetryCheck -- Yes --> IncAttempt["attempt += 1"] --> CallLLM
    RetryCheck -- No --> SyntaxErr([GherkinGenerationError:\nSyntax validation failed])

    SyntaxOk -- Yes --> ValidateRefs["_validate_primitive_references():\nCheck tool/resource/prompt names\nagainst DiscoveryResult"]
    ValidateRefs --> RefsOk{All references\nvalid?}
    RefsOk -- Yes --> ReturnOk
    RefsOk -- No --> StripInvalid["_strip_invalid_scenarios():\nRemove scenarios with\nunknown tool/prompt names\n(keep invalid resource URIs\nfor error-case tests)"]
    StripInvalid --> SetRefWarning["Set reference warning"]
    SetRefWarning --> ReturnOk

    ReturnOk([Output: (gherkin_content, warning)])

    style Start fill:#e8f5e9
    style ReturnOk fill:#e8f5e9
    style NoGherkin fill:#ffcdd2
    style SyntaxErr fill:#ffcdd2
```

## Integration Feature Generation Flow

```mermaid
flowchart TD
    Start([_generate_integration_feature]) --> Semaphore["Acquire semaphore"]
    Semaphore --> CollectPrims["Collect all primitive names\nfrom integration_scenarios"]
    CollectPrims --> QueryCtx["_query_code_context()\n— query with all primitive names joined"]
    QueryCtx --> BuildSummary["_build_primitives_summary():\nFor each primitive, look up in\ndiscovery and format details\n(Tool schema, Resource URI, Prompt args)"]
    BuildSummary --> FormatScenarios["Format scenarios text:\n- [pattern] title (primitives: ...)"]
    FormatScenarios --> RenderPrompt["Render INTEGRATION_HUMAN template:\n• scenarios list\n• primitives_summary\n• code_context"]
    RenderPrompt --> AppendStepLib["_append_step_reuse_context():\n1. Append CANONICAL_STEP_LIBRARY\n2. Append already-used steps"]
    AppendStepLib --> GenValidate["_generate_and_validate(\nhuman_content, 'integration')"]
    GenValidate --> WriteFile["Write integration_workflows.feature"]
    WriteFile --> End([Output: file path + optional warning])

    style Start fill:#e8f5e9
    style End fill:#e8f5e9
```
