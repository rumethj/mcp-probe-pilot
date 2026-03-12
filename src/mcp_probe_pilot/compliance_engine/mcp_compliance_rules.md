# MCP 2025-11-25 Compliance Rules

This document lists every schema rule enforced by the `ComplianceValidator`.
Each rule maps to a specific requirement in the
[MCP 2025-11-25 specification](https://modelcontextprotocol.io/specification/2025-11-25).

---

## 1. Base JSON-RPC 2.0 Envelope

**Spec reference:** [Overview — Messages](https://modelcontextprotocol.io/specification/2025-11-25/basic#messages)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `jsonrpc-version` | error | Every response and notification MUST have `"jsonrpc": "2.0"`. |
| `response-id-present` | error | Result responses MUST include an `id` field. |
| `response-id-match` | error | Response `id` MUST match the corresponding request `id`. |
| `result-xor-error` | error | A response MUST contain either `result` or `error`, not both. |
| `result-or-error-required` | error | A response MUST contain either `result` or `error`. |
| `missing-response` | error | Every request MUST receive a response. |
| `missing-result` | error | Response MUST contain a `result` field when no `error` is present. |

### Error Object

**Spec reference:** [Overview — Error Responses](https://modelcontextprotocol.io/specification/2025-11-25/basic#messages)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `error-is-object` | error | The `error` field MUST be an object. |
| `error-code-required` | error | Error object MUST include `code`. |
| `error-code-integer` | error | `error.code` MUST be an integer. |
| `error-message-required` | error | Error object MUST include `message`. |
| `error-message-string` | error | `error.message` MUST be a string. |

### Notifications

**Spec reference:** [Overview — Notifications](https://modelcontextprotocol.io/specification/2025-11-25/basic#messages)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `notification-no-id` | error | Notifications MUST NOT include an `id` field. |

---

## 2. `initialize` — InitializeResult

**Spec reference:** [Lifecycle — Initialization](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle#initialization)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `initialize-protocolVersion-required` | error | Result MUST contain `protocolVersion`. |
| `initialize-protocolVersion-type` | error | `protocolVersion` MUST be a string. |
| `initialize-capabilities-required` | error | Result MUST contain `capabilities`. |
| `initialize-capabilities-type` | error | `capabilities` MUST be an object. |
| `initialize-serverInfo-required` | error | Result MUST contain `serverInfo`. |
| `initialize-serverInfo-type` | error | `serverInfo` MUST be an object (Implementation). |

### serverInfo (Implementation)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `initialize-serverInfo-name-required` | error | `serverInfo` MUST contain `name`. |
| `initialize-serverInfo-name-type` | error | `serverInfo.name` MUST be a string. |
| `initialize-serverInfo-version-required` | error | `serverInfo` MUST contain `version`. |
| `initialize-serverInfo-version-type` | error | `serverInfo.version` MUST be a string. |

Optional fields: `title` (string), `description` (string), `websiteUrl` (URI string), `icons` (Icon[]).

---

## 3. `tools/list` — ListToolsResult

**Spec reference:** [Tools — Listing Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#listing-tools)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `tools-list-tools-required` | error | Result MUST contain `tools`. |
| `tools-list-tools-type` | error | `tools` MUST be an array. |
| `tool-is-object` | error | Each tool entry MUST be an object. |
| `tool-name-required` | error | Each tool MUST have `name`. |
| `tool-name-type` | error | `name` MUST be a string. |
| `tool-inputSchema-required` | error | Each tool MUST have `inputSchema`. |
| `tool-inputSchema-type` | error | `inputSchema` MUST be a valid JSON Schema object (not null). |
| `nextCursor-type` | warning | `nextCursor`, if present, MUST be a string. |

Optional tool fields: `title`, `description`, `icons`, `outputSchema`, `annotations`, `execution`.

---

## 4. `tools/call` — CallToolResult

**Spec reference:** [Tools — Calling Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#calling-tools)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `tools-call-content-required` | error | Result MUST contain `content`. |
| `tools-call-content-type` | error | `content` MUST be an array. |
| `content-block-is-object` | error | Each content block MUST be an object. |
| `content-block-type-required` | error | Each content block MUST have `type`. |
| `tools-call-isError-type` | warning | `isError`, if present, MUST be a boolean. |

### Content Block Subtypes

| Rule ID | Applies To | Severity | Requirement |
|---------|-----------|----------|-------------|
| `text-content-text-required` | TextContent | error | MUST have `text`. |
| `text-content-text-type` | TextContent | error | `text` MUST be a string. |
| `image-content-data-required` | ImageContent | error | MUST have `data`. |
| `image-content-mimeType-required` | ImageContent | error | MUST have `mimeType`. |
| `audio-content-data-required` | AudioContent | error | MUST have `data`. |
| `audio-content-mimeType-required` | AudioContent | error | MUST have `mimeType`. |
| `embedded-resource-required` | EmbeddedResource | error | MUST have `resource` object. |
| `embedded-resource-uri-required` | EmbeddedResource | error | `resource` MUST have `uri`. |
| `embedded-resource-content-required` | EmbeddedResource | error | `resource` MUST have `text` or `blob`. |
| `resource-link-uri-required` | ResourceLink | error | MUST have `uri`. |

Optional: `structuredContent` (object), `annotations`.

---

## 5. `resources/list` — ListResourcesResult

**Spec reference:** [Resources — Listing Resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources#listing-resources)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `resources-list-resources-required` | error | Result MUST contain `resources`. |
| `resources-list-resources-type` | error | `resources` MUST be an array. |
| `resource-is-object` | error | Each resource entry MUST be an object. |
| `resource-uri-required` | error | Each resource MUST have `uri`. |
| `resource-uri-type` | error | `uri` MUST be a string. |
| `resource-name-required` | error | Each resource MUST have `name`. |
| `resource-name-type` | error | `name` MUST be a string. |
| `nextCursor-type` | warning | `nextCursor`, if present, MUST be a string. |

Optional resource fields: `title`, `description`, `mimeType`, `size`, `icons`, `annotations`.

---

## 6. `resources/read` — ReadResourceResult

**Spec reference:** [Resources — Reading Resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources#reading-resources)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `resources-read-contents-required` | error | Result MUST contain `contents`. |
| `resources-read-contents-type` | error | `contents` MUST be an array. |
| `resource-content-is-object` | error | Each content item MUST be an object. |
| `resource-content-uri-required` | error | Each content item MUST have `uri`. |
| `resource-content-uri-type` | error | `uri` MUST be a string. |
| `resource-content-text-or-blob` | error | Each content item MUST contain either `text` or `blob`. |

Content items are either `TextResourceContents` (with `text` string) or `BlobResourceContents` (with `blob` base64 string). Optional: `mimeType`.

---

## 7. `prompts/list` — ListPromptsResult

**Spec reference:** [Prompts — Listing Prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts#listing-prompts)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `prompts-list-prompts-required` | error | Result MUST contain `prompts`. |
| `prompts-list-prompts-type` | error | `prompts` MUST be an array. |
| `prompt-is-object` | error | Each prompt entry MUST be an object. |
| `prompt-name-required` | error | Each prompt MUST have `name`. |
| `prompt-name-type` | error | `name` MUST be a string. |
| `prompt-arguments-type` | error | `arguments`, if present, MUST be an array. |
| `prompt-argument-name-required` | error | Each prompt argument MUST have `name`. |
| `nextCursor-type` | warning | `nextCursor`, if present, MUST be a string. |

Optional prompt fields: `title`, `description`, `icons`.

---

## 8. `prompts/get` — GetPromptResult

**Spec reference:** [Prompts — Getting a Prompt](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts#getting-a-prompt)

| Rule ID | Severity | Requirement |
|---------|----------|-------------|
| `prompts-get-messages-required` | error | Result MUST contain `messages`. |
| `prompts-get-messages-type` | error | `messages` MUST be an array. |
| `prompt-message-is-object` | error | Each PromptMessage MUST be an object. |
| `prompt-message-role-required` | error | Each PromptMessage MUST have `role`. |
| `prompt-message-role-value` | error | `role` MUST be `"user"` or `"assistant"`. |
| `prompt-message-content-required` | error | Each PromptMessage MUST have `content`. |

Optional: `description` (string).

PromptMessage content is a ContentBlock (TextContent, ImageContent, AudioContent, or EmbeddedResource).
