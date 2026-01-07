2. State-of-the-Art
2.1. The Model Context Protocol
As stated previously, a major bottleneck in configuring interaction between LLMs and external data was the “N x M” problem. This problem mirrors that of how Integrated Development Environments (IDEs) interact with language-specific tools, to which Microsoft (n.d.) introduced a solution of the Language Server Protocol (LSP). In a workshop at the AI Engineer Summit 2025, Mahesh Murag (2025), a Member of Technical Staff at Anthropic, drew parallels between MCP and its predecessor protocols regarding how they standardized how different software systems interact. One of these was the LSP, which he stated was a major inspiration in the development of the MCP(Further discussed in section 2.2.3). In the same workshop, Murag highlighted the benefits of MCP for key stakeholders in the AI ecosystem: application developers, tool/API developers, end-users, and enterprises. 


Figure 2: How AI Ecosystem Stakeholders Can Utilize MCP (Murag, 2025)

This wide-reaching influence underscores the critical importance of Quality Assurance (QA) for MCP servers, as failures could negatively affect a vast network of stakeholders. Murag also described the core client-server architecture and primitives, which are further elaborated in Anthropic’s official documentation (Anthropic, n.d.-e). Drawing from this documentation, the core features of the Model Context Protocol are illustrated in Table 3 and Table 4:

Core Server Features

Feature
Explanation
Examples
Who controls it
Tools
Functions that your LLM can actively call, and decides when to use them based on user requests. Tools can write to databases, call external APIs, modify files, or trigger other logic.
Search flights
Send messages
Create calendar events
Model
Resources
Passive data sources that provide read-only access to information for context, such as file contents, database schemas, or API documentation.
Retrieve documents
Access knowledge bases
Read calendars
Application
Prompts
Pre-built instruction templates that tell the model to work with specific tools and resources.
Plan a vacation
Summarize my meetings
Draft an email
User

Table 3: MCP Server Features (Anthropic, n.d.-d)

Core Client Features

Feature
Explanation
Example
Sampling
Sampling allows servers to request LLM completions through the client, enabling an agentic workflow. This approach puts the client in complete control of user permissions and security measures.
A server for booking travel may send a list of flights to an LLM and request that the LLM pick the best flight for the user.
Roots
Roots allow clients to specify which directories servers should focus on, communicating intended scope through a coordination mechanism.
A server for booking travel may be given access to a specific directory, from which it can read a user’s calendar.
Elicitation
Elicitation enables servers to request specific information from users during interactions, providing a structured way for servers to gather information on demand.
A server booking travel may ask for the user’s preferences on airplane seats, room type or their contact number to finalise a booking.

Table 4: MCP Client Features (Anthropic, n.d.-c)

The documentation provides a comprehensive overview of the design of these features, yielding the essential insight required for this research to address the functional validation of MCP servers. 

Additionally, Anthropic (n.d.-b) introduced the “MCP Inspector”, an interactive developer tool for testing and debugging MCP servers. While the documentation offers a detailed guide on using the Inspector and outlines best practices for server development, significant limitations remain. Testing features via the Inspector requires time-consuming manual effort. It lacks functionality for test automation and does not generate test reports.

Recent research contributions highlight the status and evolutionary trajectory of the MCP ecosystem. Guo et al. (2025) and Ray (2025) systematically analysed the MCP ecosystem through examinations of the MCP specification, developments and applications. Although neither study directly emphasizes the significance of automated functional testing, the need for it is implied by their call for suitable governance and validation frameworks, particularly within enterprise environments. Although, notably, Oribe (2025)  did remark on the need for improved tooling for advanced debugging and testing, which is what this research will address.
2.2. Methodologies in Automated Testing of Analogous Domains
Given the nascent stage of MCP, the literature on evaluating MCP servers is currently limited. However, protocol’s architecture and functional characteristics share parallels with several established domains. To derive a robust testing strategy for MCP Servers, this study analyzes existing testing frameworks in two such analogous domains: RESTful APIs and the Language Server Protocol (LSP).
2.2.1. RESTful API (REpresentational State Transfer)
Golmohammadi, Zhang & Arcuri (2023) conducted a systematic survey of the state-of-the-art in RESTful API testing up to the year of the study. Using a "snowballing" technique to ensure a comprehensive collection of literature, the authors examined methodologies used for testing in addition to case studies of their application in the real-world. This broad survey serves as a foundational reference for deriving methodologies applicable to MCP testing.
Golmohammadi et al. (2023) emphasized the difficulty in verifying the correctness of APIs due to their dependencies on network communication, data setup and external system mocking. This research likewise anticipates challenges in verifying the correctness of MCP servers, given similar dependencies. The survey highlighted several automated testing methodologies relevant to this research:

White-box and black-box testing: While white-box testing leverages knowledge of internal structures and black-box testing relies solely on external interfaces. Notably, Golmohammadi et al. (2023) found that hybrid “grey-box” approaches yielded the most effective results.
Search-based testing: This approach utilizes metaheuristic search techniques, such as Genetic and Swarm Algorithms, to resolve software testing problems. It offers viable techniques for optimizing automated test case design in MCP.
Property-based Testing: This method validates the System Under Test (SUT) against invariant properties. It is particularly valuable for schema validation and ensuring adherence to specifications.

In addition to the survey, a recent empirical work provided specific evaluation metrics for automated testing tools: RESTgym (Corradini, Pasqua & Ceccato., 2025), a framework designed to empirically assess the performance of REST API testing tools. These metrics are:

Code Coverage: The extent to which the source code is executed by a testing tool.
Operational Coverage: The extent to which system operations are successfully executed by the testing tool.
Fault Detection: The ability of the tool to trigger internal errors. 
(While RESTgym extends fault detection to measure the magnitude of unique error messages, this metric requires a complex setup process (Corradini et al., 2025). Therefore, due to resource constraints and implementation complexity, this study will focus on binary fault detection rather than error magnitude.)

Furthermore, Le et al. (2024) derived a novel AI-driven approach to autonomously generate test cases to validate RESTful APIs. Le et al. (2024) demonstrated how inter-dependencies can be identified utilizing an Operation Dependency Graph (ODG) construction algorithm. This methodology can be adapted to predict and validate expected tool-chaining behaviours by MCP clients.
2.2.3. Language Server Protocol (LSP)
MCP is architecturally a sibling to LSP: both protocols track context while maintaining persistent, stateful connections. Consequently, this study examined literature regarding LSP as well. Although the literature specifically targeting LSP server testing was scarce, Zhu et al. (2025) had addressed this gap with LSPFuzz, a grey-box fuzzer. LSPFuzz adopted techniques of “fuzzing” (discussed below) in a two-stage process: it first performs syntax-aware mutations to produce diverse code, which serves as the foundation for exploring LSP server behaviour; second, it performs context-aware fuzzing by dispatching editor operations that specifically target constructs within the source code produced in the first stage (Zhu et al., 2025).
2.3. Evaluation Frameworks Related to MCP and AI Agents

Fuzz Testing
A recurring theme in the methodologies mentioned in the reviewed literature is the use of “fuzzing”. Fuzzing refers to a testing technique that involves injecting invalid, unexpected or random data into a system or software to find bugs, crashes and security vulnerabilities (Milev, Balunovic, Baader & Vechev., 2025).

Utilizing fuzzing techniques for testing tools used by LLMs has proven effective, as found by Milev et al. (2025). The methodologies employed by ToolFuzz (Milev et al., 2025) align closely with the objectives of this study. ToolFuzz (Milev et al., 2025) incorporates two primary techniques for error detection:

Runtime Failure Detection: Utilizing partial knowledge of the tools’ semantics ( through tool documentation and/or source code), ToolFuzz generates “fuzzed” but natural prompts specifically designed to discover "breaking" inputs.
Correctness Failure Detection: To validate output correctness, the framework generates synonymous prompts and applies a cascade of consistency and correctness checks throughout the process. It employs an “LLM Oracle”, which will generate its own expected outputs and judge the agent's response against them. This ensures that the “correctness” of output is validated comprehensively.

Notably, the grey-box and white-box implementations of ToolFuzz yielded superior results compared to black-box approaches, corroborating the findings in API testing discussed in Section 2.2.1.

While ToolFuzz could be considered ideal for LLM tool testing, in the context of MCPs it will not comprehensively cover the server's internal adherence to protocol specifications nor some of the other specific functional primitives such as sampling.

In outlining the gap that ToolFuzz seeks to address, the authors note that much of the existing literature at the time focused primarily on the reasoning and planning abilities of the LLM rather than evaluating the tools and their accompanying documentation. Similarly, in the MCP domain, there exists a number of studies on evaluating LLMs or agents' ability to use tools in MCP environments; however, there is no established framework for evaluating the MCP server itself. The following section discusses these existing frameworks and highlights how their objectives diverge from those of the present study.

MCP-RADAR (Gao et al., 2025)
MCP-RADAR focuses on utilization efficiency and task distinctness. It separates evaluation into "Precise Answer" tasks (requiring factual accuracy) and "Fuzzy Match" tasks (evaluating the semantic correctness of tool selection sequences). It uniquely introduces the Computational Resource Efficiency (CRE) metric alongside standard accuracy metrics (Result Accuracy - RA). This methodology is designed to differentiate between an LLM’s reasoning capabilities and rote knowledge, effectively serving as a proficiency exam that rewards agents for solving tasks accurately with the minimal necessary computational "cost" (tokens and time).

MCPToolBench++ (Fan et al., 2025)
MCPToolBench++ targets scale and syntactic compliance. Built on a marketplace of over 4,000 servers, it evaluates the agent's ability to interpret diverse schemas and handle long context windows populated by thousands of tool definitions. Its primary metrics, Abstract Syntax Tree (AST) Accuracy and Directed Acyclic Graph(DAG) Accuracy, measure the agent's ability to generate syntactically correct API calls and formulate multi-step plans in a high-noise environment.


MCPBench (Wang et al., 2025) and MCP-Universe (Luo et al., 2025)
MCP-Bench and MCP-Universe focus on complex reasoning and environmental dynamics. MCP-Bench utilizes "fuzzy instructions" (requests without explicit tool names) to test an agent's ability to infer dependency chains across connected tools, utilizing an "LLM-as-a-Judge" to score planning quality. MCP-Universe extends this to dynamic, real-world environments (e.g., live GitHub issues), evaluating the agent's adaptability to "unknown" tools and temporal changes using execution-based success rates.


The fundamental divergence between the above and the current study lies in the subject of evaluation. In all four frameworks, the "Primary Goal" is explicitly defined as evaluating the LLM or Agent. In these setups, the MCP server is treated as the static "ground truth" or test fixture. If a task fails, the failure is attributed to the Agent (e.g., poor planning, hallucination, or syntax error). Functional server validation requires the inverse relationship: the Agent (or input pattern) must be the static fixture, and the failure must be attributed to the Server (e.g., logic error, schema violation, or crash). None of the reviewed frameworks isolates the server’s performance as the dependent variable. The challenge of staticizing the LLM/Agent will be addressed in this study. There is currently no "State of the Art" framework designed to validate the MCP server itself. This research project addresses this critical gap by proposing an automated framework specifically for Server-Centric functional validation, ensuring that MCP implementations are robust, compliant, and functionally correct before they are deployed to the marketplace.
