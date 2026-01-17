"""Base agent interface and common types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentStatus(Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentContext:
    """Context passed between agents during task execution.

    This context object carries all necessary information for agents
    to make decisions and execute actions.
    """
    task_id: str
    instruction: str
    device_id: str | None = None
    screenshot: bytes | None = None
    screen_info: dict[str, Any] | None = None
    ui_elements: list[dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    total_steps: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def add_history(self, action: str, result: dict[str, Any]) -> None:
        """Add an action to the history."""
        self.history.append({
            "step": self.current_step,
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })

    def get_last_action(self) -> dict[str, Any] | None:
        """Get the last action from history."""
        return self.history[-1] if self.history else None


@dataclass
class AgentResult:
    """Result returned by an agent after execution.

    Contains the outcome of agent execution including any actions taken,
    data extracted, and status information.
    """
    success: bool
    status: AgentStatus = AgentStatus.COMPLETED
    message: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    next_step: str | None = None
    confidence: float = 1.0
    error: str | None = None
    duration_ms: int | None = None

    @classmethod
    def success_result(
        cls,
        message: str = "Success",
        actions: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
        next_step: str | None = None,
        confidence: float = 1.0
    ) -> "AgentResult":
        """Create a successful result."""
        return cls(
            success=True,
            status=AgentStatus.COMPLETED,
            message=message,
            actions=actions or [],
            data=data or {},
            next_step=next_step,
            confidence=confidence
        )

    @classmethod
    def failure_result(
        cls,
        error: str,
        message: str = "Failed"
    ) -> "AgentResult":
        """Create a failure result."""
        return cls(
            success=False,
            status=AgentStatus.FAILED,
            message=message,
            error=error
        )


class BaseAgent(ABC):
    """Abstract base class for all AI agents.

    All agents in the system must inherit from this class and implement
    the execute method. Agents are responsible for specific tasks in the
    automation pipeline.
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's task.

        Args:
            context: The current execution context

        Returns:
            AgentResult containing the outcome of execution
        """
        pass

    async def pre_execute(self, context: AgentContext) -> None:
        """Hook called before execute. Override for setup logic."""
        self.status = AgentStatus.RUNNING

    async def post_execute(self, context: AgentContext, result: AgentResult) -> None:
        """Hook called after execute. Override for cleanup logic."""
        self.status = result.status

    async def run(self, context: AgentContext) -> AgentResult:
        """Run the agent with pre/post hooks.

        This is the main entry point for running an agent. It handles
        the execution lifecycle including pre/post hooks and error handling.
        """
        start_time = datetime.now()
        try:
            await self.pre_execute(context)
            result = await self.execute(context)
            await self.post_execute(context, result)
            result.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return result
        except Exception as e:
            self.status = AgentStatus.FAILED
            return AgentResult.failure_result(
                error=str(e),
                message=f"Agent {self.name} failed with exception"
            )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, status={self.status.value})"
