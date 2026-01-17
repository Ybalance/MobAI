"""Agent Orchestrator - Coordinates agent workflow for task execution."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from mobile_use.domain.services.agents.base import (
    AgentContext,
    AgentResult,
    AgentStatus,
    BaseAgent,
)
from mobile_use.domain.services.agents.action_executor import ActionExecutorAgent
from mobile_use.domain.services.agents.context_analyzer import ContextAnalyzerAgent
from mobile_use.domain.services.agents.result_validator import ResultValidatorAgent
from mobile_use.domain.services.agents.task_planner import TaskPlannerAgent


class OrchestratorState(Enum):
    """Orchestrator execution state."""
    IDLE = "idle"
    PLANNING = "planning"
    ANALYZING = "analyzing"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExecutionResult:
    """Result of orchestrated task execution."""
    success: bool
    task_id: str
    instruction: str
    steps_executed: int = 0
    total_steps: int = 0
    duration_ms: int = 0
    actions: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    state: OrchestratorState = OrchestratorState.COMPLETED


class AgentOrchestrator:
    """Orchestrates the execution of multiple agents for task automation.

    The orchestrator manages the workflow between different agents:
    1. TaskPlanner - Decomposes instruction into steps
    2. ContextAnalyzer - Analyzes current screen state
    3. ActionExecutor - Executes device actions
    4. ResultValidator - Validates results and determines completion

    The workflow loops through analyze->execute->validate until task completion.
    """

    def __init__(
        self,
        task_planner: TaskPlannerAgent | None = None,
        context_analyzer: ContextAnalyzerAgent | None = None,
        action_executor: ActionExecutorAgent | None = None,
        result_validator: ResultValidatorAgent | None = None,
        device_controller: Any = None,
        max_iterations: int = 50,
        step_timeout_ms: int = 60000  # 增加到60秒
    ):
        self.task_planner = task_planner or TaskPlannerAgent()
        self.context_analyzer = context_analyzer or ContextAnalyzerAgent()
        self.action_executor = action_executor or ActionExecutorAgent()
        self.result_validator = result_validator or ResultValidatorAgent()
        self.device_controller = device_controller  # 保存设备控制器引用

        self.max_iterations = max_iterations
        self.step_timeout_ms = step_timeout_ms
        self.state = OrchestratorState.IDLE
        self.on_progress = None  # 进度回调函数

    async def execute_task(
        self,
        instruction: str,
        device_id: str | None = None,
        initial_screenshot: bytes | None = None,
        initial_ui_elements: list[dict[str, Any]] | None = None,
        screen_info: dict[str, Any] | None = None
    ) -> ExecutionResult:
        """Execute a complete automation task.

        Args:
            instruction: Natural language instruction
            device_id: Target device ID
            initial_screenshot: Initial screen screenshot
            initial_ui_elements: Initial UI element hierarchy
            screen_info: Screen information

        Returns:
            ExecutionResult with task outcome
        """
        import uuid
        start_time = datetime.now()
        task_id = str(uuid.uuid4())

        # Initialize context
        context = AgentContext(
            task_id=task_id,
            instruction=instruction,
            device_id=device_id,
            screenshot=initial_screenshot,
            screen_info=screen_info,
            ui_elements=initial_ui_elements or []
        )

        result = ExecutionResult(
            success=False,
            task_id=task_id,
            instruction=instruction
        )

        try:
            # 动态规划模式：每次只规划下一步
            iteration = 0
            completed_steps = []  # 已完成的步骤描述
            
            while iteration < self.max_iterations:
                iteration += 1
                
                # 每次循环前重新获取UI元素和截图
                if self.device_controller:
                    try:
                        print(f"[Orchestrator] 步骤 {iteration}: 刷新UI元素和截图...")
                        ui_elements = await self.device_controller.get_ui_hierarchy()
                        context.ui_elements = ui_elements
                        print(f"[Orchestrator] 获取到 {len(ui_elements)} 个UI元素")
                        
                        # 刷新截图
                        screenshot_result = await self.device_controller.take_screenshot()
                        if screenshot_result.success:
                            context.screenshot = screenshot_result.data.get("screenshot")
                            print(f"[Orchestrator] 截图已更新")
                    except Exception as e:
                        print(f"[Orchestrator] 获取UI/截图失败: {e}")

                # 动态规划：根据当前UI状态规划下一步
                self.state = OrchestratorState.PLANNING
                context.metadata["completed_steps"] = completed_steps
                
                plan_result = await self._run_agent_with_timeout(
                    self.task_planner, context
                )

                if not plan_result.success:
                    result.error = plan_result.error or "Planning failed"
                    result.state = OrchestratorState.FAILED
                    break

                plan = plan_result.data.get("plan", {})
                steps = plan.get("steps", [])
                
                # 检查是否任务已完成
                if not steps or plan.get("task_complete"):
                    print(f"[Orchestrator] 任务完成！")
                    result.success = True
                    result.state = OrchestratorState.COMPLETED
                    break
                
                # 只取第一个步骤执行
                next_step = steps[0]
                context.metadata["plan"] = {"steps": [next_step]}
                context.current_step = 0
                
                step_desc = next_step.get("description", f"执行步骤 {iteration}")
                step_action = next_step.get("action", "")
                
                print(f"[Orchestrator] 下一步: {step_action} - {step_desc}")
                
                step_target = next_step.get("target", "")
                if self.on_progress:
                    self.on_progress(len(completed_steps), len(completed_steps) + 1, step_action, step_desc, step_target)

                # Execute the action
                self.state = OrchestratorState.EXECUTING
                print(f"[Orchestrator] 开始执行动作...")
                exec_result = await self._run_agent_with_timeout(
                    self.action_executor, context
                )
                print(f"[Orchestrator] 执行结果: success={exec_result.success}, error={exec_result.error}")

                if not exec_result.success:
                    print(f"[Orchestrator] 执行失败: {exec_result.error}")
                    result.error = exec_result.error or "Execution failed"
                    result.state = OrchestratorState.FAILED
                    break

                # Record action
                for action in exec_result.actions:
                    result.actions.append(action)
                    context.add_history(
                        action.get("action", "unknown"),
                        action.get("result", {})
                    )

                # 记录已完成的步骤（包含详细信息）
                completed_step_info = {
                    "action": step_action,
                    "target": step_target,
                    "description": step_desc,
                    "success": True
                }
                completed_steps.append(completed_step_info)
                result.steps_executed = len(completed_steps)
                result.total_steps = len(completed_steps)  # 动态更新总步数
                context.current_step += 1

            else:
                # Max iterations reached
                result.error = f"Max iterations ({self.max_iterations}) reached"
                result.state = OrchestratorState.FAILED

        except asyncio.TimeoutError:
            result.error = "Task execution timed out"
            result.state = OrchestratorState.FAILED
        except Exception as e:
            result.error = str(e)
            result.state = OrchestratorState.FAILED

        # Calculate duration
        result.duration_ms = int(
            (datetime.now() - start_time).total_seconds() * 1000
        )
        self.state = result.state

        return result

    async def _run_agent_with_timeout(
        self,
        agent: BaseAgent,
        context: AgentContext
    ) -> AgentResult:
        """Run an agent with timeout."""
        try:
            return await asyncio.wait_for(
                agent.run(context),
                timeout=self.step_timeout_ms / 1000
            )
        except asyncio.TimeoutError:
            return AgentResult.failure_result(
                error=f"Agent {agent.name} timed out",
                message="Timeout"
            )

    async def _try_recovery(
        self,
        context: AgentContext,
        failed_result: AgentResult
    ) -> bool:
        """Attempt to recover from a failed validation.

        Returns True if recovery was successful.
        """
        # Simple recovery strategies
        error = failed_result.error or ""

        # Strategy 1: Retry with fresh context analysis
        if "confidence" in error.lower():
            # Re-analyze and retry
            return True

        # Strategy 2: Go back and try alternative
        if context.current_step > 0:
            # Could implement backtracking here
            pass

        return False

    def get_state(self) -> OrchestratorState:
        """Get current orchestrator state."""
        return self.state

    def get_agent_status(self) -> dict[str, str]:
        """Get status of all agents."""
        return {
            "task_planner": self.task_planner.status.value,
            "context_analyzer": self.context_analyzer.status.value,
            "action_executor": self.action_executor.status.value,
            "result_validator": self.result_validator.status.value
        }
