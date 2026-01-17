"""Task entity representing automation tasks."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class TaskStep:
    """Individual step within a task."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: str = ""
    target: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> None:
        """Mark step as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self, result: dict[str, Any] | None = None) -> None:
        """Mark step as completed."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        """Mark step as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()


@dataclass
class Task:
    """Main task entity representing an automation task."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    natural_language_input: str = ""
    device_id: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def add_step(self, action: str, target: str | None = None,
                 parameters: dict[str, Any] | None = None) -> TaskStep:
        """Add a new step to the task."""
        step = TaskStep(
            action=action,
            target=target,
            parameters=parameters or {}
        )
        self.steps.append(step)
        return step

    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def cancel(self) -> None:
        """Cancel the task."""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()

    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def duration(self) -> float | None:
        """Get task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def progress(self) -> float:
        """Get task progress as percentage (0.0 to 1.0)."""
        if not self.steps:
            return 0.0
        completed_steps = sum(1 for step in self.steps if step.status == TaskStatus.COMPLETED)
        return completed_steps / len(self.steps)


@dataclass
class TaskResult:
    """Result of task execution."""
    
    task_id: str
    success: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] | None = None
    error: str | None = None
    duration: float | None = None
    screenshots: list[str] = field(default_factory=list)
    
    @classmethod
    def from_task(cls, task: Task) -> "TaskResult":
        """Create TaskResult from Task entity."""
        return cls(
            task_id=task.id,
            success=task.status == TaskStatus.COMPLETED,
            steps=[
                {
                    "id": step.id,
                    "action": step.action,
                    "target": step.target,
                    "status": step.status.value,
                    "result": step.result,
                    "error": step.error,
                }
                for step in task.steps
            ],
            error=task.error,
            duration=task.duration,
        )
