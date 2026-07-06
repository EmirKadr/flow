"""Apphjälpens tool-paket: register, read-only-tools och function calling-loop.

Import av domänmodulerna registrerar deras tools i registret.
"""
from .common import ToolInputError
from .registry import (
    AssistantTool,
    all_tools,
    allowed_tools_for,
    openai_tool_declarations,
    register_tool,
    run_tool,
    tool_by_name,
)
from . import core_tools  # noqa: F401  (registrerar tools vid import)
from . import person_tools  # noqa: F401
from . import schedule_tools  # noqa: F401
from . import productivity_tools  # noqa: F401
from . import history_tools  # noqa: F401
from . import finance_tools  # noqa: F401
from . import system_tools  # noqa: F401
from .runtime import ToolLoopResult, run_tool_loop

__all__ = [
    "AssistantTool",
    "ToolInputError",
    "ToolLoopResult",
    "all_tools",
    "allowed_tools_for",
    "openai_tool_declarations",
    "register_tool",
    "run_tool",
    "run_tool_loop",
    "tool_by_name",
]
