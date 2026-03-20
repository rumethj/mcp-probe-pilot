# Sequence Diagram — Planning Stage

This diagram shows the Planning Stage flow. The **core** participants are: **MCPProbeOrchestrator**, **Planner**, **LLMClient**, and **LLM** (ChatGoogleGenerativeAI), so that who drives planning, who performs it, who provides the model, and who is actually invoked are all visible.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Planner as Planner
    participant LLMCtx as LLMClient
    participant LLM as LLM (ChatGoogleGenerativeAI)

    rect rgb(245, 245, 255)
        Note over Orch, LLM: Unit test planning
        Orch ->> Orch: require discovery_result
        Orch ->> LLMCtx: with LLMClient()
        activate LLMCtx
        LLMCtx -->> Orch: llm
        Orch ->> Planner: Planner(llm)
        activate Planner

        loop for each tool in discovery_result.tools
            Orch ->> Planner: plan_tool_unit_tests(tool)
            Planner ->> LLM: chain.invoke(tool_name, tool_description, input_schema)
            LLM -->> Planner: _ScenarioListOutput(scenarios)
            Planner -->> Orch: list[ScenarioPlan]
        end
        loop for each resource in discovery_result.resources
            Orch ->> Planner: plan_resource_unit_tests(resource)
            Planner ->> LLM: chain.invoke(resource_uri, description, …)
            LLM -->> Planner: _ScenarioListOutput(scenarios)
            Planner -->> Orch: list[ScenarioPlan]
        end
        loop for each prompt in discovery_result.prompts
            Orch ->> Planner: plan_prompt_unit_tests(prompt_info)
            Planner ->> LLM: chain.invoke(prompt_name, description, arguments)
            LLM -->> Planner: _ScenarioListOutput(scenarios)
            Planner -->> Orch: list[ScenarioPlan]
        end

        Orch ->> Orch: UnitTestPlanResult(tool_scenarios, resource_scenarios, prompt_scenarios)
        deactivate Planner
        Orch ->> LLMCtx: __exit__
        deactivate LLMCtx
    end

    rect rgb(250, 248, 255)
        Note over Orch, LLM: Integration test planning
        Orch ->> LLMCtx: with LLMClient()
        activate LLMCtx
        LLMCtx -->> Orch: llm
        Orch ->> Planner: Planner(llm)
        activate Planner
        Orch ->> Planner: plan_integration_tests(discovery_result)
        Planner ->> Planner: _summarise_tools/resources/prompts(discovery_result)
        Planner ->> LLM: chain.invoke(tools_summary, resources_summary, prompts_summary)
        LLM -->> Planner: IntegrationTestPlanResult(integration_scenarios)
        Planner -->> Orch: IntegrationTestPlanResult
        deactivate Planner
        Orch ->> LLMCtx: __exit__
        deactivate LLMCtx
    end
```

## Summary

| Step | Orchestrator action | Main interaction |
|------|---------------------|------------------|
| **Unit test planning** | Requires `discovery_result`. `with LLMClient()` → `Planner(llm)`; for each tool/resource/prompt calls `plan_*_unit_tests(…)`. | Planner builds a prompt + structured-output chain and invokes the LLM per primitive; returns `list[ScenarioPlan]`. Orchestrator aggregates into `UnitTestPlanResult`. |
| **Integration test planning** | Same LLM context; calls `planner.plan_integration_tests(discovery_result)`. | Planner summarises discovery, invokes LLM once with structured output `IntegrationTestPlanResult`, returns it to Orchestrator. |

---

## Other classes you might include

You can extend the diagram with any of the following, depending on how much you want to show.

| Class | Why include it |
|-------|----------------|
| **DiscoveryResult** | Planning is entirely driven by discovery output: unit planning iterates over `discovery_result.tools`, `.resources`, `.prompts`, and integration planning takes the whole `DiscoveryResult` for summaries. Showing it as a participant (e.g. Orchestrator reading from it before each `plan_*` call) makes that data dependency explicit. |
| **UnitTestPlanResult** / **IntegrationTestPlanResult** | These are the main outputs of the stage. Usually they appear as return values in the diagram; adding them as participants is only useful if you want to emphasise that the orchestrator stores and later passes them to the Generation stage. |
| **ScenarioPlan** | The atomic unit of a plan (scenario title + primitives). Again, typically shown as payload in messages rather than as a lifeline, unless you want to highlight the shape of the data. |
| **Prompts** (e.g. `plan/prompts.py` constants) | The Planner uses `TOOL_UNIT_SYSTEM`, `TOOL_UNIT_HUMAN`, `RESOURCE_*`, `PROMPT_*`, `INTEGRATION_*` to build the chat prompt. Including “Prompts” as a participant could show that the Planner “reads” prompt templates before each LLM call, if you want to document prompt provenance. |

If you tell me which of these you want in the diagram (e.g. “add DiscoveryResult and the two result types”), I can update the sequence diagram to include them explicitly.
