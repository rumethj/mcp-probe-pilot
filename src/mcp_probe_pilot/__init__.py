"""MCP-Probe-Pilot: Automated testing framework for MCP server validation.

This package provides tools for:
- Test generation from MCP server discovery and source code analysis
- Fuzzing and edge case testing
- BDD test execution with protocol compliance validation
- LLM-powered semantic assertion evaluation
- Failure classification and report generation
"""

__version__ = "0.1.0"
__author__ = "MCP-Probe Team"

from mcp_probe_pilot.config import MCPProbeConfig, LLMConfig, load_config

__all__ = [
    "__version__",
    "MCPProbeConfig",
    "LLMConfig",
    "load_config",
]
