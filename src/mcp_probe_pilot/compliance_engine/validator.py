"""MCP 2025-11-25 compliance validator for captured JSON-RPC traffic.

Reads a traffic log (mcp-traffic.json) produced by the recording MCPClient,
validates every server response against the official MCP specification, and
returns a structured ComplianceReport.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp_probe_pilot.compliance_engine.models import (
    ComplianceReport,
    ExchangeViolation,
    ScenarioComplianceResult,
)

logger = logging.getLogger(__name__)

SPEC_VERSION = "2025-11-25"


class ComplianceValidator:
    """Validates captured MCP JSON-RPC traffic against the 2025-11-25 spec."""

    _METHOD_VALIDATORS: dict[str, str] = {
        "initialize": "_validate_initialize",
        "tools/list": "_validate_tools_list",
        "tools/call": "_validate_tools_call",
        "resources/list": "_validate_resources_list",
        "resources/read": "_validate_resources_read",
        "prompts/list": "_validate_prompts_list",
        "prompts/get": "_validate_prompts_get",
    }

    def validate_file(self, traffic_path: Path) -> ComplianceReport:
        """Load a traffic JSON file and validate all scenarios."""
        if not traffic_path.exists():
            logger.warning("Traffic file not found: %s", traffic_path)
            return ComplianceReport()

        with open(traffic_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self.validate_traffic(data)

    def validate_traffic(self, data: dict[str, Any]) -> ComplianceReport:
        """Validate a pre-loaded traffic dict (``{"scenarios": [...]}``)."""
        scenarios = data.get("scenarios", [])
        results: list[ScenarioComplianceResult] = []

        for scenario_data in scenarios:
            results.append(self._validate_scenario(scenario_data))

        return ComplianceReport(scenarios=results)

    def _validate_scenario(
        self, scenario_data: dict[str, Any]
    ) -> ScenarioComplianceResult:
        feature_name = scenario_data.get("feature_name", "unknown")
        scenario_name = scenario_data.get("scenario_name", "unknown")
        exchanges = scenario_data.get("exchanges", [])

        violations: list[ExchangeViolation] = []

        for idx, exchange in enumerate(exchanges):
            violations.extend(self._validate_exchange(idx, exchange))

        return ScenarioComplianceResult(
            feature_name=feature_name,
            scenario_name=scenario_name,
            total_exchanges=len(exchanges),
            violations=violations,
        )

    def _validate_exchange(
        self, idx: int, exchange: dict[str, Any]
    ) -> list[ExchangeViolation]:
        ex_type = exchange.get("type", "")
        method = exchange.get("method", "")

        if ex_type in ("notification", "server_notification"):
            return self._validate_notification(idx, exchange)

        if ex_type == "request_response":
            return self._validate_request_response(idx, method, exchange)

        return []

    # ------------------------------------------------------------------
    # Notification validation
    # ------------------------------------------------------------------

    def _validate_notification(
        self, idx: int, exchange: dict[str, Any]
    ) -> list[ExchangeViolation]:
        msg = exchange.get("message", {})
        violations: list[ExchangeViolation] = []
        method = exchange.get("method", "")

        if msg.get("jsonrpc") != "2.0":
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="jsonrpc-version",
                message="Notification must have \"jsonrpc\": \"2.0\".",
                path="jsonrpc",
            ))

        if "id" in msg:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="notification-no-id",
                message="Notifications MUST NOT include an id field.",
                path="id",
            ))

        return violations

    # ------------------------------------------------------------------
    # Request / Response validation
    # ------------------------------------------------------------------

    def _validate_request_response(
        self,
        idx: int,
        method: str,
        exchange: dict[str, Any],
    ) -> list[ExchangeViolation]:
        response = exchange.get("response")
        request = exchange.get("request", {})
        violations: list[ExchangeViolation] = []

        if response is None:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="missing-response",
                message="No response received for request.",
            ))
            return violations

        violations.extend(self._validate_jsonrpc_envelope(idx, method, request, response))

        if "error" in response:
            violations.extend(self._validate_error_object(idx, method, response["error"]))
            return violations

        result = response.get("result")
        if result is None:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="missing-result",
                message="Response must contain a 'result' field when no 'error' is present.",
                path="result",
            ))
            return violations

        validator_name = self._METHOD_VALIDATORS.get(method)
        if validator_name:
            validator_fn = getattr(self, validator_name)
            violations.extend(validator_fn(idx, result))

        return violations

    def _validate_jsonrpc_envelope(
        self,
        idx: int,
        method: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []

        if response.get("jsonrpc") != "2.0":
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="jsonrpc-version",
                message="Response must have \"jsonrpc\": \"2.0\".",
                path="jsonrpc",
            ))

        resp_id = response.get("id")
        req_id = request.get("id")
        if resp_id is None:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="response-id-present",
                message="Result response MUST include an id field.",
                path="id",
            ))
        elif req_id is not None and resp_id != req_id:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="response-id-match",
                message=f"Response id ({resp_id}) does not match request id ({req_id}).",
                path="id",
            ))

        has_result = "result" in response
        has_error = "error" in response
        if has_result and has_error:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="result-xor-error",
                message="Response must contain either 'result' or 'error', not both.",
            ))
        if not has_result and not has_error:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="result-or-error-required",
                message="Response must contain either 'result' or 'error'.",
            ))

        return violations

    def _validate_error_object(
        self,
        idx: int,
        method: str,
        error: Any,
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []

        if not isinstance(error, dict):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="error-is-object",
                message="Error field must be an object.",
                path="error",
            ))
            return violations

        if "code" not in error:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="error-code-required",
                message="Error object MUST include 'code'.",
                path="error.code",
            ))
        elif not isinstance(error["code"], int):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="error-code-integer",
                message="Error code MUST be an integer.",
                path="error.code",
            ))

        if "message" not in error:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="error-message-required",
                message="Error object MUST include 'message'.",
                path="error.message",
            ))
        elif not isinstance(error["message"], str):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="error-message-string",
                message="Error message MUST be a string.",
                path="error.message",
            ))

        return violations

    # ------------------------------------------------------------------
    # Method-specific validators
    # ------------------------------------------------------------------

    def _validate_initialize(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "initialize"

        for field in ("protocolVersion", "capabilities", "serverInfo"):
            if field not in result:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule=f"initialize-{field}-required",
                    message=f"InitializeResult MUST contain '{field}'.",
                    path=f"result.{field}",
                ))

        pv = result.get("protocolVersion")
        if pv is not None and not isinstance(pv, str):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="initialize-protocolVersion-type",
                message="protocolVersion MUST be a string.",
                path="result.protocolVersion",
            ))

        caps = result.get("capabilities")
        if caps is not None and not isinstance(caps, dict):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="initialize-capabilities-type",
                message="capabilities MUST be an object.",
                path="result.capabilities",
            ))

        server_info = result.get("serverInfo")
        if server_info is not None:
            if not isinstance(server_info, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="initialize-serverInfo-type",
                    message="serverInfo MUST be an object.",
                    path="result.serverInfo",
                ))
            else:
                for si_field in ("name", "version"):
                    if si_field not in server_info:
                        violations.append(ExchangeViolation(
                            exchange_index=idx,
                            method=method,
                            rule=f"initialize-serverInfo-{si_field}-required",
                            message=f"serverInfo MUST contain '{si_field}'.",
                            path=f"result.serverInfo.{si_field}",
                        ))
                    elif not isinstance(server_info[si_field], str):
                        violations.append(ExchangeViolation(
                            exchange_index=idx,
                            method=method,
                            rule=f"initialize-serverInfo-{si_field}-type",
                            message=f"serverInfo.{si_field} MUST be a string.",
                            path=f"result.serverInfo.{si_field}",
                        ))

        return violations

    def _validate_tools_list(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "tools/list"

        if "tools" not in result:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="tools-list-tools-required",
                message="ListToolsResult MUST contain 'tools' array.",
                path="result.tools",
            ))
            return violations

        tools = result["tools"]
        if not isinstance(tools, list):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="tools-list-tools-type",
                message="'tools' MUST be an array.",
                path="result.tools",
            ))
            return violations

        for t_idx, tool in enumerate(tools):
            if not isinstance(tool, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="tool-is-object",
                    message=f"Tool at index {t_idx} MUST be an object.",
                    path=f"result.tools[{t_idx}]",
                ))
                continue

            if "name" not in tool:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="tool-name-required",
                    message=f"Tool at index {t_idx} MUST have 'name'.",
                    path=f"result.tools[{t_idx}].name",
                ))
            elif not isinstance(tool["name"], str):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="tool-name-type",
                    message=f"Tool name at index {t_idx} MUST be a string.",
                    path=f"result.tools[{t_idx}].name",
                ))

            if "inputSchema" not in tool:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="tool-inputSchema-required",
                    message=f"Tool at index {t_idx} MUST have 'inputSchema'.",
                    path=f"result.tools[{t_idx}].inputSchema",
                ))
            elif not isinstance(tool.get("inputSchema"), dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="tool-inputSchema-type",
                    message=f"inputSchema at index {t_idx} MUST be a valid JSON Schema object (not null).",
                    path=f"result.tools[{t_idx}].inputSchema",
                ))

        self._validate_optional_cursor(violations, idx, method, result)
        return violations

    def _validate_tools_call(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "tools/call"

        if "content" not in result:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="tools-call-content-required",
                message="CallToolResult MUST contain 'content' array.",
                path="result.content",
            ))
            return violations

        content = result["content"]
        if not isinstance(content, list):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="tools-call-content-type",
                message="'content' MUST be an array.",
                path="result.content",
            ))
            return violations

        for c_idx, block in enumerate(content):
            if not isinstance(block, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="content-block-is-object",
                    message=f"Content block at index {c_idx} MUST be an object.",
                    path=f"result.content[{c_idx}]",
                ))
                continue

            block_type = block.get("type")
            if block_type is None:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="content-block-type-required",
                    message=f"Content block at index {c_idx} MUST have 'type'.",
                    path=f"result.content[{c_idx}].type",
                ))
                continue

            violations.extend(
                self._validate_content_block(idx, method, c_idx, block, block_type)
            )

        is_error = result.get("isError")
        if is_error is not None and not isinstance(is_error, bool):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="tools-call-isError-type",
                message="isError, if present, MUST be a boolean.",
                path="result.isError",
                severity="warning",
            ))

        return violations

    def _validate_content_block(
        self,
        idx: int,
        method: str,
        c_idx: int,
        block: dict[str, Any],
        block_type: str,
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        prefix = f"result.content[{c_idx}]"

        if block_type == "text":
            if "text" not in block:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="text-content-text-required",
                    message=f"TextContent at index {c_idx} MUST have 'text'.",
                    path=f"{prefix}.text",
                ))
            elif not isinstance(block["text"], str):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="text-content-text-type",
                    message=f"TextContent.text at index {c_idx} MUST be a string.",
                    path=f"{prefix}.text",
                ))

        elif block_type == "image":
            for field in ("data", "mimeType"):
                if field not in block:
                    violations.append(ExchangeViolation(
                        exchange_index=idx,
                        method=method,
                        rule=f"image-content-{field}-required",
                        message=f"ImageContent at index {c_idx} MUST have '{field}'.",
                        path=f"{prefix}.{field}",
                    ))

        elif block_type == "audio":
            for field in ("data", "mimeType"):
                if field not in block:
                    violations.append(ExchangeViolation(
                        exchange_index=idx,
                        method=method,
                        rule=f"audio-content-{field}-required",
                        message=f"AudioContent at index {c_idx} MUST have '{field}'.",
                        path=f"{prefix}.{field}",
                    ))

        elif block_type == "resource":
            resource = block.get("resource")
            if resource is None:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="embedded-resource-required",
                    message=f"EmbeddedResource at index {c_idx} MUST have 'resource'.",
                    path=f"{prefix}.resource",
                ))
            elif isinstance(resource, dict):
                if "uri" not in resource:
                    violations.append(ExchangeViolation(
                        exchange_index=idx,
                        method=method,
                        rule="embedded-resource-uri-required",
                        message=f"Embedded resource at index {c_idx} MUST have 'uri'.",
                        path=f"{prefix}.resource.uri",
                    ))
                has_text = "text" in resource
                has_blob = "blob" in resource
                if not has_text and not has_blob:
                    violations.append(ExchangeViolation(
                        exchange_index=idx,
                        method=method,
                        rule="embedded-resource-content-required",
                        message=f"Embedded resource at index {c_idx} MUST have 'text' or 'blob'.",
                        path=f"{prefix}.resource",
                    ))

        elif block_type == "resource_link":
            if "uri" not in block:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-link-uri-required",
                    message=f"ResourceLink at index {c_idx} MUST have 'uri'.",
                    path=f"{prefix}.uri",
                ))

        return violations

    def _validate_resources_list(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "resources/list"

        if "resources" not in result:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="resources-list-resources-required",
                message="ListResourcesResult MUST contain 'resources' array.",
                path="result.resources",
            ))
            return violations

        resources = result["resources"]
        if not isinstance(resources, list):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="resources-list-resources-type",
                message="'resources' MUST be an array.",
                path="result.resources",
            ))
            return violations

        for r_idx, resource in enumerate(resources):
            if not isinstance(resource, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-is-object",
                    message=f"Resource at index {r_idx} MUST be an object.",
                    path=f"result.resources[{r_idx}]",
                ))
                continue

            if "uri" not in resource:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-uri-required",
                    message=f"Resource at index {r_idx} MUST have 'uri'.",
                    path=f"result.resources[{r_idx}].uri",
                ))
            elif not isinstance(resource["uri"], str):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-uri-type",
                    message=f"Resource uri at index {r_idx} MUST be a string.",
                    path=f"result.resources[{r_idx}].uri",
                ))

            if "name" not in resource:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-name-required",
                    message=f"Resource at index {r_idx} MUST have 'name'.",
                    path=f"result.resources[{r_idx}].name",
                ))
            elif not isinstance(resource["name"], str):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-name-type",
                    message=f"Resource name at index {r_idx} MUST be a string.",
                    path=f"result.resources[{r_idx}].name",
                ))

        self._validate_optional_cursor(violations, idx, method, result)
        return violations

    def _validate_resources_read(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "resources/read"

        if "contents" not in result:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="resources-read-contents-required",
                message="ReadResourceResult MUST contain 'contents' array.",
                path="result.contents",
            ))
            return violations

        contents = result["contents"]
        if not isinstance(contents, list):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="resources-read-contents-type",
                message="'contents' MUST be an array.",
                path="result.contents",
            ))
            return violations

        for c_idx, item in enumerate(contents):
            if not isinstance(item, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-content-is-object",
                    message=f"Content item at index {c_idx} MUST be an object.",
                    path=f"result.contents[{c_idx}]",
                ))
                continue

            if "uri" not in item:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-content-uri-required",
                    message=f"Content item at index {c_idx} MUST have 'uri'.",
                    path=f"result.contents[{c_idx}].uri",
                ))
            elif not isinstance(item["uri"], str):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-content-uri-type",
                    message=f"Content item uri at index {c_idx} MUST be a string.",
                    path=f"result.contents[{c_idx}].uri",
                ))

            has_text = "text" in item
            has_blob = "blob" in item
            if not has_text and not has_blob:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="resource-content-text-or-blob",
                    message=f"Content item at index {c_idx} MUST contain either 'text' or 'blob'.",
                    path=f"result.contents[{c_idx}]",
                ))

        return violations

    def _validate_prompts_list(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "prompts/list"

        if "prompts" not in result:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="prompts-list-prompts-required",
                message="ListPromptsResult MUST contain 'prompts' array.",
                path="result.prompts",
            ))
            return violations

        prompts = result["prompts"]
        if not isinstance(prompts, list):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="prompts-list-prompts-type",
                message="'prompts' MUST be an array.",
                path="result.prompts",
            ))
            return violations

        for p_idx, prompt in enumerate(prompts):
            if not isinstance(prompt, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-is-object",
                    message=f"Prompt at index {p_idx} MUST be an object.",
                    path=f"result.prompts[{p_idx}]",
                ))
                continue

            if "name" not in prompt:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-name-required",
                    message=f"Prompt at index {p_idx} MUST have 'name'.",
                    path=f"result.prompts[{p_idx}].name",
                ))
            elif not isinstance(prompt["name"], str):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-name-type",
                    message=f"Prompt name at index {p_idx} MUST be a string.",
                    path=f"result.prompts[{p_idx}].name",
                ))

            arguments = prompt.get("arguments")
            if arguments is not None:
                if not isinstance(arguments, list):
                    violations.append(ExchangeViolation(
                        exchange_index=idx,
                        method=method,
                        rule="prompt-arguments-type",
                        message=f"Prompt arguments at index {p_idx} MUST be an array.",
                        path=f"result.prompts[{p_idx}].arguments",
                    ))
                else:
                    for a_idx, arg in enumerate(arguments):
                        if isinstance(arg, dict) and "name" not in arg:
                            violations.append(ExchangeViolation(
                                exchange_index=idx,
                                method=method,
                                rule="prompt-argument-name-required",
                                message=f"Prompt argument at [{p_idx}][{a_idx}] MUST have 'name'.",
                                path=f"result.prompts[{p_idx}].arguments[{a_idx}].name",
                            ))

        self._validate_optional_cursor(violations, idx, method, result)
        return violations

    def _validate_prompts_get(
        self, idx: int, result: dict[str, Any]
    ) -> list[ExchangeViolation]:
        violations: list[ExchangeViolation] = []
        method = "prompts/get"

        if "messages" not in result:
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="prompts-get-messages-required",
                message="GetPromptResult MUST contain 'messages' array.",
                path="result.messages",
            ))
            return violations

        messages = result["messages"]
        if not isinstance(messages, list):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="prompts-get-messages-type",
                message="'messages' MUST be an array.",
                path="result.messages",
            ))
            return violations

        valid_roles = {"user", "assistant"}
        for m_idx, msg in enumerate(messages):
            if not isinstance(msg, dict):
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-message-is-object",
                    message=f"PromptMessage at index {m_idx} MUST be an object.",
                    path=f"result.messages[{m_idx}]",
                ))
                continue

            role = msg.get("role")
            if role is None:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-message-role-required",
                    message=f"PromptMessage at index {m_idx} MUST have 'role'.",
                    path=f"result.messages[{m_idx}].role",
                ))
            elif role not in valid_roles:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-message-role-value",
                    message=f"PromptMessage role at index {m_idx} MUST be 'user' or 'assistant', got '{role}'.",
                    path=f"result.messages[{m_idx}].role",
                ))

            if "content" not in msg:
                violations.append(ExchangeViolation(
                    exchange_index=idx,
                    method=method,
                    rule="prompt-message-content-required",
                    message=f"PromptMessage at index {m_idx} MUST have 'content'.",
                    path=f"result.messages[{m_idx}].content",
                ))

        return violations

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_optional_cursor(
        violations: list[ExchangeViolation],
        idx: int,
        method: str,
        result: dict[str, Any],
    ) -> None:
        cursor = result.get("nextCursor")
        if cursor is not None and not isinstance(cursor, str):
            violations.append(ExchangeViolation(
                exchange_index=idx,
                method=method,
                rule="nextCursor-type",
                message="nextCursor, if present, MUST be a string.",
                path="result.nextCursor",
                severity="warning",
            ))
