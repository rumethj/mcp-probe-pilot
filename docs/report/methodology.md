 Methodology
3.1. Design Approach 
The core design philosophy of this research is to treat the MCP server as the "System Under Test" (SUT) and the Client (the AI agent) in this case as a deterministic, static test fixture(or at least with minimal non-determinism). To manage time and implementation complexity, the artefact produced will be restricted to testing MCP servers implemented in Python. The designed tool will follow a two-staged process as outlined in a high-level sequence diagram in Figure 3.


Figure 3: MCP Testing Framework High-Level Sequence Diagram

The research objectives outlined in section 1.2 will follow the approaches and acceptance criteria for completion:
Objective 1: Define Functional Correctness
Approach

State-of-the-art literature has identified some categorization approaches to faults as discussed in section 2 (State of the art). However, some of these categorizations lack sufficient specificity and further investigations are required to validate their applicability within the context of MCP.

Acceptance Criteria

Specific measurable fault categories are identified. (eg: Schema violations, functional failures)
Attributes of faults are clearly defined per category.

Objective 2: Design Specification-Based Compliance Engine
Approach

A “Compliance Engine” module should be developed, which will act as a middleware interceptor, validating every payload sent and received by the server against the official schema before functional logic is evaluated. 

Acceptance Criteria

The framework must automatically flag any server response that deviates from the JSON-RPC or MCP schema.
The framework must achieve a 100% detection rate for deliberately injected schema errors (e.g., missing required fields, malformed URIs) in a controlled test environment.
Objective 3: Formulate Deterministic Functional Testing
Approach

This is the core development objective, and therefore, to achieve it, this study should allocate more focus and time here. From initial investigations(Section 2), it seemed suitable to utilize a hybrid-testing approach in processes of the system, such as test case synthesis and test execution. Specific component-wise methodology/technique selection, however, must be carefully considered. Therefore, in this study, an experimental approach will be taken to verify the suitability of specific methodologies.

Acceptance Criteria

The framework must be able to infer tool dependencies (e.g., calling auth_login before get_data)
The framework can autonomously generate comprehensive re-executable test cases/ templates. (Single-turn and multi-turn)
The framework must be able to produce identical pass/fail results across multiple runs (zero stochastic variation).

Objective 4: Evaluate Functional Error Handling and Boundary Conditions
Approach

The framework will incorporate Fuzz Testing techniques. This will involve injecting invalid data types, boundary values (e.g., empty strings, integer overflows), and malformed JSON into tool arguments to verify the server returns standard error codes rather than crashing or exposing stack traces. Fuzz testing’s suitability is evident through its recurring implementations in autonomous testing frameworks such as ToolFuzz (Milev et al., 2025).

Acceptance Criteria

The framework must create test cases with permutations of valid, invalid arguments to check invalidity and edge cases.
The framework must distinguish between "Graceful Failures" (correct error codes) and "Critical Failures" (server crash/timeout).
The framework must verify correct error-handling implementations of MCP servers when invalid or boundary value arguments are passed.
Objective 5: Operational Feasibility via CI Integration
Approach

The system's implementation will be designed to be cloud-native to allow easy integration into cloud-native CI/CD pipeline tools such as Tekton (Continuous Delivery Foundation, n.d.). Additionally, it will generate reports in standard format compatible with existing visualization dashboards.

Acceptance Criteria
The framework must successfully execute within a headless CI environment.
The framework should outputs legible Test Incident Reports, providing human-readable summaries of passed/failed tests.

3.2. Development Methodology
The ScrumBan (Scrum and Kanban) methodology (Atlassian, n.d.) will be used for the development of this project. This approach incorporates components of each methodology while forgoing the activities such as sprint planning and sprint ceremonies, which provide diminishing returns in a single-developer environment. Kanban’s practice of using cards to denote units of work, organized on a Kanban board, will be employed to easily visualize the project status. Furthermore, Scrum’s methodology of dividing projects into sprints, with a focus on delivering a working iteration or component, allows the developer to maintain a steady workflow and ensure regular, incremental progress. On completion of each sprint, the delivered iteration will be presented to the project supervisor for review and feedback. Adhering to such an agile development approach allows for flexible development, where tasks can be iteratively revised during the implementation phase to refine the final outcome.

Outlined below are the expected iterations of the artefact to be developed.

Iteration 1 (Foundation): Setup of the basic project architecture and connection handling.
Iteration 2 (Compliance): Implementation of the Schema Validation Engine.
Iteration 3 (Generation and Execution): Development of the AI-driven test case generator.
Iteration 4 (Integration): CI/CD pipeline integration and reporting.

Figure 4: Excerpt of Sprint-wise Task Allocation
3.3. Testing and Evaluation Plan
To validate the effectiveness of the proposed testing framework, an initial meta-evaluation strategy is outlined below. It is important to note that this evaluation plan represents the current research intent; however, given the exploratory nature of the project, as the research progresses and testing constraints emerge, these evaluation methods and metrics may be refined or expanded upon.

Case Studies

Custom Server: A custom Python MCP server will be developed with intentional defects injected (e.g., logic errors, broken schemas, unhandled exceptions). The framework will be evaluated on its ability to detect and correctly categorize these injected faults.
Reference Implementation: Additionally, the framework will be run against the existing open-source server implementation. 

Evaluation Metrics

The framework’s performance will be measured against the following metrics:

Fault Detection Ratio: The ratio of actual bugs (injected or existing) successfully identified by the tool.
Answer Relevance: Measured via similarity between the server's actual output and the "ground truth" expectation defined in the test case.
Answer Format Compliance: A binary metric determining if the server's output structure allows the LLM to parse it correctly (contextual precision).