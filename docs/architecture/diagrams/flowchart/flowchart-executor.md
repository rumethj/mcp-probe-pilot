# Executor Stage — Internal Flowchart

## Overview

The Executor creates an isolated virtual environment, installs all test dependencies, runs `behave` against each generated `.feature` file, and parses the JSON output into structured results. All test execution is fully deterministic with no LLM calls at runtime.

## Environment Setup Flow

```mermaid
flowchart TD
    Start([Start: setup_environment]) --> CreateVenv["_create_venv()"]
    CreateVenv --> VenvExists{Python binary exists at\n.mcp-probe-venv/bin/python?}
    VenvExists -- Yes --> ReuseVenv["Log: reusing existing venv"]
    VenvExists -- No --> RunUV["subprocess.run:\nuv venv .mcp-probe-venv\n--python sys.executable"]
    RunUV --> VenvOk{returncode == 0?}
    VenvOk -- No --> VenvErr([ExecutorError:\nFailed to create venv])
    VenvOk -- Yes --> VenvCreated["Venv created successfully"]

    ReuseVenv --> InstallDeps
    VenvCreated --> InstallDeps

    InstallDeps["_install_dependencies()"]
    InstallDeps --> HasDeps{Dependencies\nlist non-empty?}
    HasDeps -- No --> SkipDeps["Log: no dependencies"]
    HasDeps -- Yes --> RunInstall["subprocess.run:\nuv pip install\n--python .mcp-probe-venv/bin/python\nbehave mcp>=1.0.0 ..."]
    RunInstall --> InstallOk{returncode == 0?}
    InstallOk -- No --> InstallErr([ExecutorError:\nFailed to install deps])
    InstallOk -- Yes --> DepsInstalled["Dependencies installed"]

    SkipDeps --> InstallReqs
    DepsInstalled --> InstallReqs

    InstallReqs["_install_requirements()"]
    InstallReqs --> ReqExists{features/requirements.txt\nexists?}
    ReqExists -- No --> Done["Setup complete"]
    ReqExists -- Yes --> RunReqInstall["subprocess.run:\nuv pip install\n--python .mcp-probe-venv/bin/python\n-r features/requirements.txt"]
    RunReqInstall --> ReqOk{returncode == 0?}
    ReqOk -- No --> ReqErr([ExecutorError:\nFailed to install from\nrequirements.txt])
    ReqOk -- Yes --> Done

    Done([Environment ready])

    style Start fill:#e8f5e9
    style Done fill:#e8f5e9
    style VenvErr fill:#ffcdd2
    style InstallErr fill:#ffcdd2
    style ReqErr fill:#ffcdd2
```

## Test Execution Flow

```mermaid
flowchart TD
    Start([Start: run_tests]) --> CheckPython{Venv python\nexists?}
    CheckPython -- No --> NoVenvErr([ExecutorError:\nCall setup_environment first])
    CheckPython -- Yes --> CheckFeatures{features/ directory\nexists?}
    CheckFeatures -- No --> NoFeatErr([ExecutorError:\nFeatures directory not found])
    CheckFeatures -- Yes --> CleanResults["Delete previous\ntest-results.json\nif exists"]

    CleanResults --> SetTarget{"feature_file\nprovided?"}
    SetTarget -- Yes --> SingleTarget["target = feature_file path"]
    SetTarget -- No --> AllTarget["target = features/ directory"]

    SingleTarget --> BuildEnv
    AllTarget --> BuildEnv

    BuildEnv["_build_env():\n• Copy os.environ\n• Set VIRTUAL_ENV = .mcp-probe-venv\n• Prepend .mcp-probe-venv/bin to PATH"]

    BuildEnv --> RunBehave["subprocess.run:\npython -m behave <target>\n--format json\n--outfile test-results.json\n--no-capture\n\ncwd = repo_root\ntimeout = 300s\nenv = built environment"]

    RunBehave --> TimedOut{TimeoutExpired?}
    TimedOut -- Yes --> TimeoutResult["Return TestExecutionResult:\nsuccess=False\nstderr='timed out after 300s'"]

    TimedOut -- No --> CheckExit{"returncode\n!= 0?"}
    CheckExit -- Yes --> LogWarning["Log: behave exited\nwith non-zero code\n(test failures, not fatal)"]
    CheckExit -- No --> ParseResults

    LogWarning --> ParseResults

    ParseResults["_parse_results(proc)"]
    ParseResults --> ReadJSON{"test-results.json\nexists?"}
    ReadJSON -- Yes --> LoadJSON["json.loads(file content)"]
    ReadJSON -- No --> EmptyJSON["raw_json = []"]

    LoadJSON --> ParseOk{Valid JSON?}
    ParseOk -- No --> EmptyJSON
    ParseOk -- Yes --> IterateFeatures

    EmptyJSON --> IterateFeatures

    IterateFeatures["For each feature in JSON"]
    IterateFeatures --> IterateElements["For each element\n(type == 'scenario')"]
    IterateElements --> IterateSteps["For each step in scenario"]

    IterateSteps --> CheckStepStatus{"step result\nstatus?"}
    CheckStepStatus -- passed --> AccumDuration["Accumulate duration"]
    CheckStepStatus -- failed --> MarkFailed["scenario_status = 'failed'"]
    CheckStepStatus -- "undefined/error" --> MarkErrored["scenario_status = 'errored'"]
    CheckStepStatus -- skipped --> MarkSkipped["scenario_status = 'skipped'\n(only if still 'passed')"]

    AccumDuration --> MoreSteps{More steps?}
    MarkFailed --> MoreSteps
    MarkErrored --> MoreSteps
    MarkSkipped --> MoreSteps
    MoreSteps -- Yes --> IterateSteps
    MoreSteps -- No --> TallyScenario{"scenario_status?"}

    TallyScenario -- passed --> IncPassed["passed += 1"]
    TallyScenario -- failed --> IncFailed["failed += 1"]
    TallyScenario -- errored --> IncErrored["errored += 1"]
    TallyScenario -- skipped --> IncSkipped["skipped += 1"]

    IncPassed --> MoreElements{More scenarios?}
    IncFailed --> MoreElements
    IncErrored --> MoreElements
    IncSkipped --> MoreElements
    MoreElements -- Yes --> IterateElements
    MoreElements -- No --> MoreFeatureBlocks{More features?}
    MoreFeatureBlocks -- Yes --> IterateFeatures
    MoreFeatureBlocks -- No --> BuildResult

    BuildResult["Build TestExecutionResult:\n• success (returncode == 0)\n• total_scenarios\n• passed, failed, errored, skipped\n• duration (total accumulated)\n• raw_json (preserved)\n• output_file path\n• stdout, stderr"]

    BuildResult --> End([Output: TestExecutionResult])
    TimeoutResult --> End

    style Start fill:#e8f5e9
    style End fill:#e8f5e9
    style NoVenvErr fill:#ffcdd2
    style NoFeatErr fill:#ffcdd2
```

## Per-Feature Execution Loop (CLI Level)

```mermaid
flowchart TD
    Start([Start: CLI execution loop]) --> ParseFeatures["validate_and_format_feature_files()\n→ GherkinFeatureCollection"]
    ParseFeatures --> FeatureLoop["For each .feature file"]
    FeatureLoop --> CreateExec["Create TestExecutor(\nrepo_root, dependencies, timeout=300)"]
    CreateExec --> Setup["setup_environment()\n(reuses existing venv)"]
    Setup --> Run["run_tests(feature_file)"]
    Run --> Report["Report per-feature results:\n✓ passed / ✗ failed / ! errored / ○ skipped"]
    Report --> MoreFeatures{More .feature\nfiles?}
    MoreFeatures -- Yes --> FeatureLoop
    MoreFeatures -- No --> Aggregate["Aggregate all results\nacross features"]
    Aggregate --> End([Pipeline execution complete])

    style Start fill:#e8f5e9
    style End fill:#e8f5e9
```
