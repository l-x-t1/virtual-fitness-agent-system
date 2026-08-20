from __future__ import annotations

from typing import Any

from app.tools.agent import FitnessToolAgent
from app.tools.exercise_tool import ExerciseTool
from app.tools.mcp_adapter import MCPAdapter
from app.tools.pose_tool import PoseEvaluationTool
from app.tools.registry import ToolRegistry, tool_result
from app.tools.venue_tool import VenueTool
from app.tools.weather_tool import WeatherTool


def build_fitness_tool_registry(
    *,
    actor: dict[str, Any] | None = None,
    weather: WeatherTool | None = None,
    venue: VenueTool | None = None,
    pose: PoseEvaluationTool | None = None,
    exercise: ExerciseTool | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register((weather or WeatherTool()).spec())
    for spec in (venue or VenueTool()).specs():
        registry.register(spec)
    registry.register((pose or PoseEvaluationTool()).spec())
    for spec in (exercise or ExerciseTool(actor=actor)).specs():
        registry.register(spec)
    return registry


__all__ = [
    "ExerciseTool", "FitnessToolAgent", "MCPAdapter", "PoseEvaluationTool",
    "ToolRegistry", "VenueTool", "WeatherTool", "build_fitness_tool_registry",
    "tool_result",
]
