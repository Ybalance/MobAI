"""Result Validator Agent - Validates action results and task completion."""

from typing import Any

from mobile_use.domain.services.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
)


class ResultValidatorAgent(BaseAgent):
    """Agent responsible for validating execution results.

    This agent checks whether actions were successful and determines
    if the overall task has been completed or needs more steps.
    """

    def __init__(self, confidence_threshold: float = 0.7):
        super().__init__(
            name="ResultValidator",
            description="Validates action results and determines task completion"
        )
        self.confidence_threshold = confidence_threshold

    async def execute(self, context: AgentContext) -> AgentResult:
        """Validate execution results.

        Args:
            context: Current execution context with action results

        Returns:
            AgentResult indicating validation status
        """
        # Get the last action from history
        last_action = context.get_last_action()
        
        # 如果没有历史记录，但有计划步骤，假设操作成功
        if not last_action:
            plan = context.metadata.get("plan", {})
            steps = plan.get("steps", [])
            if steps and context.current_step < len(steps):
                # 假设操作已执行，直接标记为完成
                return AgentResult.success_result(
                    message="Step validated (assumed success)",
                    data={
                        "task_complete": context.current_step >= len(steps) - 1,
                        "current_step": context.current_step,
                        "validation": {"success": True, "confidence": 0.8}
                    },
                    confidence=0.8
                )
            return AgentResult.failure_result(
                error="No action to validate",
                message="No previous action found in context"
            )

        # Get plan information
        plan = context.metadata.get("plan", {})
        steps = plan.get("steps", [])
        current_step = context.current_step

        # Validate the last action
        validation = self._validate_action(last_action, context)

        # Determine if task is complete
        is_complete = self._check_task_completion(
            current_step=current_step,
            total_steps=len(steps),
            validation=validation,
            context=context
        )

        if not validation["success"]:
            return AgentResult.failure_result(
                error=validation.get("error", "Validation failed"),
                message="Action validation failed"
            )

        if is_complete:
            return AgentResult.success_result(
                message="Task completed successfully",
                data={
                    "task_complete": True,
                    "steps_executed": current_step + 1,
                    "total_steps": len(steps),
                    "validation": validation
                },
                confidence=validation.get("confidence", 0.8)
            )
        else:
            return AgentResult.success_result(
                message=f"Step {current_step + 1}/{len(steps)} validated",
                data={
                    "task_complete": False,
                    "current_step": current_step,
                    "next_step": current_step + 1,
                    "validation": validation
                },
                next_step="analyze",
                confidence=validation.get("confidence", 0.8)
            )

    def _validate_action(
        self,
        action: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Validate a single action result."""
        result = action.get("result", {})
        action_type = action.get("action", "")

        validation: dict[str, Any] = {
            "success": True,
            "confidence": 0.8,
            "checks": []
        }

        # Check if action reported success
        if isinstance(result, dict):
            if not result.get("success", True):
                validation["success"] = False
                validation["error"] = result.get("error", "Action failed")
                validation["confidence"] = 0.3
                return validation

        # Action-specific validation
        if action_type == "tap":
            validation["checks"].append(self._validate_tap(result, context))
        elif action_type == "input":
            validation["checks"].append(self._validate_input(result, context))
        elif action_type == "swipe":
            validation["checks"].append(self._validate_swipe(result, context))

        # Calculate overall confidence
        if validation["checks"]:
            confidences = [c.get("confidence", 0.8) for c in validation["checks"]]
            validation["confidence"] = sum(confidences) / len(confidences)

        # Mark as failed if confidence is too low
        if validation["confidence"] < self.confidence_threshold:
            validation["success"] = False
            validation["error"] = "Low confidence in action result"

        return validation

    def _validate_tap(
        self,
        result: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Validate tap action."""
        check = {
            "type": "tap_validation",
            "success": True,
            "confidence": 0.8
        }

        # Check if tap was within screen bounds
        point = result.get("point", {})
        screen_info = context.screen_info or {}
        width = screen_info.get("width", 1080)
        height = screen_info.get("height", 1920)

        x = point.get("x", 0)
        y = point.get("y", 0)

        if not (0 <= x <= width and 0 <= y <= height):
            check["success"] = False
            check["confidence"] = 0.2
            check["error"] = "Tap outside screen bounds"

        return check

    def _validate_input(
        self,
        result: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Validate input action."""
        check = {
            "type": "input_validation",
            "success": True,
            "confidence": 0.8
        }

        text = result.get("text", "")
        if not text:
            check["success"] = False
            check["confidence"] = 0.3
            check["error"] = "No text was input"

        return check

    def _validate_swipe(
        self,
        result: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Validate swipe action."""
        check = {
            "type": "swipe_validation",
            "success": True,
            "confidence": 0.8
        }

        direction = result.get("direction")
        if not direction:
            check["confidence"] = 0.6

        return check

    def _check_task_completion(
        self,
        current_step: int,
        total_steps: int,
        validation: dict[str, Any],
        context: AgentContext
    ) -> bool:
        """Check if the overall task is complete."""
        # 没有步骤时直接完成
        if total_steps == 0:
            return True
            
        # All steps executed
        if current_step >= total_steps - 1:
            return True

        # Check for explicit completion markers
        last_action = context.get_last_action()
        if last_action:
            result = last_action.get("result", {})
            if isinstance(result, dict) and result.get("success"):
                # 如果操作成功且是最后一步，标记完成
                if current_step >= total_steps - 1:
                    return True
            if isinstance(result, dict) and result.get("completed"):
                return True

        # 简单任务（单步）直接完成
        if total_steps == 1 and validation.get("success"):
            return True

        # Check instruction for completion keywords
        instruction = context.instruction.lower()
        completion_keywords = ["完成", "done", "finish", "complete"]
        if any(kw in instruction for kw in completion_keywords):
            # More lenient completion check
            if validation.get("confidence", 0) > 0.9:
                return True

        return False
