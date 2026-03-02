"""Test-plan generation via LLM structured output.

Produces ScenarioPlan lists for unit tests (per-primitive) and
IntegrationTestPlanResult for cross-primitive workflow scenarios.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate

from mcp_probe_pilot.core.models.plan import (
    IntegrationTestPlanResult,
    ScenarioPlan,
)
from mcp_probe_pilot.plan.prompts import (
    INTEGRATION_HUMAN,
    INTEGRATION_SYSTEM,
    PROMPT_UNIT_HUMAN,
    PROMPT_UNIT_SYSTEM,
    RESOURCE_UNIT_HUMAN,
    RESOURCE_UNIT_SYSTEM,
    TOOL_UNIT_HUMAN,
    TOOL_UNIT_SYSTEM,
)

if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI

    from mcp_probe_pilot.core.models.discovery import (
        DiscoveryResult,
        PromptInfo,
        ResourceInfo,
        ToolInfo,
    )

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field


class _ScenarioListOutput(BaseModel):
    """LLM structured-output wrapper for a list of scenario titles."""

    scenarios: list[str] = Field(
        ..., description="List of BDD Scenario titles"
    )


class Planner:
    """Generates test plans by prompting an LLM with MCP primitive schemas."""

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        self._llm = llm

    # ------------------------------------------------------------------
    # Unit-test planning (one primitive at a time)
    # ------------------------------------------------------------------

    def plan_tool_unit_tests(self, tool: ToolInfo) -> list[ScenarioPlan]:
        """Generate unit-test scenario plans for a single MCP tool."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", TOOL_UNIT_SYSTEM),
            ("human", TOOL_UNIT_HUMAN),
        ])
        chain = prompt | self._llm.with_structured_output(_ScenarioListOutput)
        result: _ScenarioListOutput = chain.invoke({
            "tool_name": tool.name,
            "tool_description": tool.description or "",
            "input_schema": json.dumps(tool.input_schema, indent=2),
        })
        return [
            ScenarioPlan(scenario=title, primitives=[tool.name])
            for title in result.scenarios
        ]

    def plan_resource_unit_tests(
        self, resource: ResourceInfo
    ) -> list[ScenarioPlan]:
        """Generate unit-test scenario plans for a single MCP resource."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", RESOURCE_UNIT_SYSTEM),
            ("human", RESOURCE_UNIT_HUMAN),
        ])
        chain = prompt | self._llm.with_structured_output(_ScenarioListOutput)
        result: _ScenarioListOutput = chain.invoke({
            "resource_uri": resource.uri,
            "resource_name": resource.name or "",
            "resource_description": resource.description or "",
            "mime_type": resource.mime_type or "unspecified",
            "is_template": str(resource.is_template),
        })
        identifier = resource.name or resource.uri
        return [
            ScenarioPlan(scenario=title, primitives=[identifier])
            for title in result.scenarios
        ]

    def plan_prompt_unit_tests(
        self, prompt_info: PromptInfo
    ) -> list[ScenarioPlan]:
        """Generate unit-test scenario plans for a single MCP prompt."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", PROMPT_UNIT_SYSTEM),
            ("human", PROMPT_UNIT_HUMAN),
        ])
        chain = prompt | self._llm.with_structured_output(_ScenarioListOutput)
        args_repr = ", ".join(
            f"{a.name} ({'required' if a.required else 'optional'})"
            for a in prompt_info.arguments
        ) or "none"
        result: _ScenarioListOutput = chain.invoke({
            "prompt_name": prompt_info.name,
            "prompt_description": prompt_info.description or "",
            "arguments": args_repr,
        })
        return [
            ScenarioPlan(scenario=title, primitives=[prompt_info.name])
            for title in result.scenarios
        ]

    # ------------------------------------------------------------------
    # Integration-test planning (all primitives together)
    # ------------------------------------------------------------------

    def plan_integration_tests(
        self, discovery: DiscoveryResult
    ) -> IntegrationTestPlanResult:
        """Identify cross-primitive integration-test workflow scenarios."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", INTEGRATION_SYSTEM),
            ("human", INTEGRATION_HUMAN),
        ])
        chain = prompt | self._llm.with_structured_output(
            IntegrationTestPlanResult
        )
        result: IntegrationTestPlanResult = chain.invoke({
            "tools_summary": self._summarise_tools(discovery),
            "resources_summary": self._summarise_resources(discovery),
            "prompts_summary": self._summarise_prompts(discovery),
        })
        return result

    # ------------------------------------------------------------------
    # Helpers to build capability summaries for integration prompts
    # ------------------------------------------------------------------

    @staticmethod
    def _summarise_tools(discovery: DiscoveryResult) -> str:
        if not discovery.tools:
            return "No tools discovered."
        lines: list[str] = []
        for t in discovery.tools:
            lines.append(
                f"- **{t.name}**: {t.description or 'No description'}\n"
                f"  Input Schema: {json.dumps(t.input_schema, indent=2)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _summarise_resources(discovery: DiscoveryResult) -> str:
        if not discovery.resources:
            return "No resources discovered."
        lines: list[str] = []
        for r in discovery.resources:
            template_tag = " (template)" if r.is_template else ""
            lines.append(
                f"- **{r.name or r.uri}**{template_tag}: "
                f"{r.description or 'No description'} "
                f"[{r.mime_type or 'unspecified'}]"
            )
        return "\n".join(lines)

    @staticmethod
    def _summarise_prompts(discovery: DiscoveryResult) -> str:
        if not discovery.prompts:
            return "No prompts discovered."
        lines: list[str] = []
        for p in discovery.prompts:
            args = ", ".join(
                f"{a.name} ({'required' if a.required else 'optional'})"
                for a in p.arguments
            ) or "none"
            lines.append(
                f"- **{p.name}**: {p.description or 'No description'}\n"
                f"  Arguments: {args}"
            )
        return "\n".join(lines)
