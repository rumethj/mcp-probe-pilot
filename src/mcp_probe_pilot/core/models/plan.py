"""Pydantic models for test planning output."""

from typing import Optional

from pydantic import BaseModel, Field


class ScenarioPlan(BaseModel):
    """A single BDD test scenario plan, used for both unit and integration tests."""

    scenario: str = Field(
        ..., description="BDD scenario title (becomes the Gherkin Scenario: line)"
    )
    primitives: list[str] = Field(
        default_factory=list,
        description="Related MCP primitive names (1 for unit tests, multiple for integration)",
    )
    pattern: Optional[str] = Field(
        None,
        description="Workflow pattern type for integration tests: "
        "prompt-driven | resource-augmented | chain-of-thought",
    )


class UnitTestPlanResult(BaseModel):
    """Aggregated unit test plans across all MCP primitive types."""

    tool_scenarios: list[ScenarioPlan] = Field(default_factory=list)
    resource_scenarios: list[ScenarioPlan] = Field(default_factory=list)
    prompt_scenarios: list[ScenarioPlan] = Field(default_factory=list)

    @property
    def num_scenarios(self) -> int:
        return (
            len(self.tool_scenarios)
            + len(self.resource_scenarios)
            + len(self.prompt_scenarios)
        )
    
    @property
    def scenario_plans(self) -> list[dict]:
        # Group scenario by primitive type and name
        scenario_plans =[]
        
        # Initialize with the base category key 
        tool_scenario_plan = {"tools": {}}
        for scenario in self.tool_scenarios:
            # Iterate over the primitives list (since primitive_name doesn't exist)
            for prim in scenario.primitives:
                # setdefault safely initializes a new list if the primitive isn't in the dict yet
                tool_scenario_plan["tools"].setdefault(prim,[]).append(scenario.scenario)
        scenario_plans.append(tool_scenario_plan)
        
        resource_scenario_plan = {"resources": {}}
        for scenario in self.resource_scenarios:
            for prim in scenario.primitives:
                resource_scenario_plan["resources"].setdefault(prim,[]).append(scenario.scenario)
        scenario_plans.append(resource_scenario_plan)
        
        prompt_scenario_plan = {"prompts": {}}
        for scenario in self.prompt_scenarios:
            for prim in scenario.primitives:
                prompt_scenario_plan["prompts"].setdefault(prim,[]).append(scenario.scenario)
        scenario_plans.append(prompt_scenario_plan)
        
        return scenario_plans

    def get_scenario_plans(self, primitive_type: str, primitive_name: str) -> list[ScenarioPlan]:

        if primitive_type == "tool":
            return [scenario for scenario in self.tool_scenarios if primitive_name in scenario.primitives]
        elif primitive_type == "resource":
            return [scenario for scenario in self.resource_scenarios if primitive_name in scenario.primitives]
        elif primitive_type == "prompt":
            return [scenario for scenario in self.prompt_scenarios if primitive_name in scenario.primitives]
        else:
            raise ValueError(f"Invalid primitive type: {primitive_type}")

class IntegrationTestPlanResult(BaseModel):
    """Integration test plans identifying cross-primitive workflow scenarios."""

    integration_scenarios: list[ScenarioPlan] = Field(default_factory=list)

    @property
    def num_scenarios(self) -> int:
        return len(self.integration_scenarios)

    @property
    def scenario_plans(self) -> list[dict]:
        # Group scenario by primitive type and name
        scenario_plans = []
        for scenario in self.integration_scenarios:
            scenario_plans.append(
                {
                    "primitives": scenario.primitives,
                    "scenario": scenario.scenario,
                }
            )
        return scenario_plans
