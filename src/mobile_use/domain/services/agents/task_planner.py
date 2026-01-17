"""Task Planner Agent - Decomposes natural language into executable steps."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from mobile_use.domain.services.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
)


class LLMProvider(Protocol):
    """Protocol for LLM providers."""
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt."""
        ...


@dataclass
class TaskStep:
    """A single step in the task plan."""
    index: int
    action: str
    target: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    expected_result: str = ""


@dataclass
class TaskPlan:
    """Complete task plan with steps."""
    instruction: str
    steps: list[TaskStep] = field(default_factory=list)
    estimated_duration_ms: int | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def add_step(
        self,
        action: str,
        target: str | None = None,
        parameters: dict[str, Any] | None = None,
        description: str = "",
        expected_result: str = ""
    ) -> TaskStep:
        """Add a step to the plan."""
        step = TaskStep(
            index=len(self.steps),
            action=action,
            target=target,
            parameters=parameters or {},
            description=description,
            expected_result=expected_result
        )
        self.steps.append(step)
        return step


class TaskPlannerAgent(BaseAgent):
    """Agent responsible for planning and decomposing tasks.

    This agent takes a natural language instruction and breaks it down
    into a series of executable steps that other agents can perform.
    """

    SYSTEM_PROMPT = """你是一个移动设备自动化任务规划助手。根据当前屏幕状态，规划下一步操作。

**任务分析：**
- "打开XXX应用" = 需要在桌面找到XXX应用图标并点击
- "搜索XXX" = 需要先进入应用，找到搜索框，输入内容
- "点击第一个视频" = 在搜索结果中点击第一个视频

**核心规则：**
1. 只能点击当前UI元素列表中**确实存在**的元素
2. 如果当前不在桌面且需要打开应用，先用home回到桌面
3. 如果目标应用不在当前屏幕，用scroll滑动桌面寻找
4. 不要点击无关元素！"互联网"、"设置"等不是哔哩哔哩！
5. 每次只返回一个步骤

**重要：判断任务是否完成**
- 只有当屏幕已经显示了用户期望的最终状态时，才设置task_complete=true
- 如果还需要执行任何操作（包括home、back等），必须先规划该操作，task_complete=false
- 例如：用户要"返回桌面"，如果当前不在桌面，必须先执行home操作，不能直接标记完成

**判断当前位置：**
- 如果UI元素包含"设置"、"WLAN"、"蓝牙"等 = 在设置页面，需要home回桌面
- 如果UI元素包含应用图标（哔哩哔哩、微信等）= 在桌面
- 如果UI元素包含"首页"、"推荐"、"搜索" = 在应用内

输出JSON格式：
{"steps": [{"action": "动作", "target": "元素名称", "parameters": {}, "description": "描述"}], "task_complete": false, "reason": "原因"}

可用操作：
- tap: 点击元素
- scroll: 滑动 (parameters: {"direction": "up/down/left/right"})
- input: 输入文本 (parameters: {"text": "内容"})
- back: 返回上一页
- home: 回到桌面（重要！迷路时用这个）

示例1 - 在错误页面，需要回桌面：
用户指令："打开哔哩哔哩"
当前UI元素：互联网、WLAN、蓝牙、设置
返回：
{"steps": [{"action": "home", "target": null, "parameters": {}, "description": "回到桌面"}], "task_complete": false, "reason": "当前在设置页面，需要先回到桌面找哔哩哔哩"}

示例2 - 在桌面，目标不在屏幕：
用户指令："打开哔哩哔哩"
当前UI元素：微信、QQ、游戏中心（桌面图标，但没有哔哩哔哩）
返回：
{"steps": [{"action": "scroll", "target": null, "parameters": {"direction": "left"}, "description": "滑动桌面寻找哔哩哔哩"}], "task_complete": false, "reason": "在桌面但没找到哔哩哔哩，滑动寻找"}

示例3 - 找到目标应用：
用户指令："打开哔哩哔哩"
当前UI元素：哔哩哔哩、微信、QQ
返回：
{"steps": [{"action": "tap", "target": "哔哩哔哩", "parameters": {}, "description": "点击哔哩哔哩"}], "task_complete": false, "reason": "找到哔哩哔哩，点击打开"}
"""

    def __init__(self, llm_provider: LLMProvider | None = None):
        super().__init__(
            name="TaskPlanner",
            description="Decomposes natural language instructions into executable steps"
        )
        self.llm_provider = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute task planning.

        Args:
            context: Current execution context with instruction

        Returns:
            AgentResult containing the task plan
        """
        instruction = context.instruction

        if not instruction:
            return AgentResult.failure_result(
                error="No instruction provided",
                message="Cannot plan without an instruction"
            )

        # 始终使用LLM规划
        if self.llm_provider:
            print(f"[TaskPlanner] 调用LLM规划: {instruction}")
            try:
                plan = await self._generate_plan_with_llm(instruction, context)
            except Exception as e:
                print(f"[TaskPlanner] LLM调用失败: {e}，使用简单规划")
                plan = self._generate_simple_plan(instruction)
        else:
            # 没有LLM时使用简单规划
            print(f"[TaskPlanner] 无LLM，使用简单规划: {instruction}")
            plan = self._generate_simple_plan(instruction)

        # 检查任务是否完成
        task_complete = plan.metadata.get("task_complete", False)
        
        if task_complete:
            return AgentResult.success_result(
                message="Task completed",
                data={
                    "plan": {
                        "instruction": plan.instruction,
                        "steps": [],
                        "task_complete": True,
                        "reason": plan.metadata.get("reason", "任务已完成")
                    }
                },
                confidence=1.0
            )

        if not plan.steps:
            return AgentResult.failure_result(
                error="Could not generate any steps",
                message="Failed to decompose instruction into steps"
            )

        return AgentResult.success_result(
            message=f"Generated next step",
            data={
                "plan": {
                    "instruction": plan.instruction,
                    "steps": [
                        {
                            "index": s.index,
                            "action": s.action,
                            "target": s.target,
                            "parameters": s.parameters,
                            "description": s.description,
                            "expected_result": s.expected_result
                        }
                        for s in plan.steps
                    ],
                    "task_complete": False,
                    "confidence": plan.confidence
                }
            },
            confidence=plan.confidence
        )

    def _is_complex_instruction(self, instruction: str) -> bool:
        """判断是否是复杂指令."""
        # 包含多个动作的连接词
        complex_keywords = ["然后", "接着", "之后", "并且", "同时", "再", "and then", "then"]
        for kw in complex_keywords:
            if kw in instruction:
                return True

        # 包含逗号分隔的多个动作
        if "，" in instruction or "," in instruction:
            return True

        # 指令长度较长通常是复杂指令
        if len(instruction) > 15:
            return True

        return False

    async def _generate_plan_with_llm(
        self,
        instruction: str,
        context: AgentContext
    ) -> TaskPlan:
        """Generate plan using LLM."""
        import json

        # 构建动态规划prompt
        prompt = f"{self.SYSTEM_PROMPT}\n\n"
        prompt += f"用户指令: {instruction}\n"
        
        # 添加已完成的步骤（详细信息）
        completed_steps = context.metadata.get("completed_steps", [])
        if completed_steps:
            prompt += "\n已完成的步骤:\n"
            for i, step in enumerate(completed_steps, 1):
                if isinstance(step, dict):
                    action = step.get("action", "")
                    target = step.get("target", "")
                    desc = step.get("description", "")
                    prompt += f"  {i}. [{action}] {desc}"
                    if target:
                        prompt += f" (目标: {target})"
                    prompt += " ✓\n"
                else:
                    prompt += f"  {i}. {step} ✓\n"
        else:
            prompt += "\n已完成的步骤: 无（这是第一步）\n"

        # 添加当前UI元素
        if context.ui_elements:
            # 优先提取可点击的有意义元素
            clickable_elements = []
            other_elements = []
            seen = set()  # 去重
            
            for e in context.ui_elements:
                text = e.get('text', '').strip()
                desc = e.get('content_desc', '').strip()
                clickable = e.get('clickable', False)
                element_name = text or desc
                
                if element_name and element_name not in seen:
                    seen.add(element_name)
                    if clickable:
                        clickable_elements.append(f"- {element_name} [可点击]")
                    else:
                        other_elements.append(f"- {element_name}")
            
            # 优先显示可点击元素，最多50个
            elements_desc = clickable_elements[:40] + other_elements[:10]
            
            if elements_desc:
                prompt += f"\n当前屏幕UI元素:\n" + "\n".join(elements_desc)
        
        prompt += "\n\n请根据以上信息，规划下一步操作（只返回一步）:"

        try:
            print(f"[TaskPlanner] 动态规划，已完成{len(completed_steps)}步")
            
            # 注意：DeepSeek 不支持图片分析，只使用文本
            # 如果需要图片分析，请切换到支持视觉的模型（如 GPT-4V、Claude 等）
            response = await self.llm_provider.generate(prompt)  # type: ignore
            
            print(f"[TaskPlanner] LLM响应: {response[:300] if response else 'Empty'}")
            
            # 尝试解析JSON
            # 有时LLM返回的JSON可能包含markdown代码块
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            
            plan_data = json.loads(json_str)
            
            # 检查任务是否完成
            task_complete = plan_data.get("task_complete", False)
            steps = plan_data.get("steps", [])
            reason = plan_data.get("reason", "")
            
            print(f"[TaskPlanner] 解析成功，步骤数: {len(steps)}, 任务完成: {task_complete}, 原因: {reason}")

            plan = TaskPlan(instruction=instruction)
            plan.metadata = {"task_complete": task_complete, "reason": reason}
            
            for step_data in steps:
                plan.add_step(
                    action=step_data.get("action", "tap"),
                    target=step_data.get("target"),
                    parameters=step_data.get("parameters", {}),
                    description=step_data.get("description", ""),
                    expected_result=step_data.get("expected_result", "")
                )
            plan.confidence = plan_data.get("confidence", 0.8)
            return plan

        except Exception as e:
            print(f"[TaskPlanner] LLM规划失败: {e}")
            print(f"[TaskPlanner] 回退到简单规划")
            return self._generate_simple_plan(instruction)

    def _generate_simple_plan(self, instruction: str) -> TaskPlan:
        """Generate a simple plan without LLM (fallback)."""
        plan = TaskPlan(instruction=instruction, confidence=0.5)

        instruction_lower = instruction.lower()

        # 高置信度的直接命令
        # 返回桌面/主页
        if any(kw in instruction_lower for kw in ["返回桌面", "回到桌面", "主页", "home", "桌面"]):
            plan.add_step(
                action="home",
                target=None,
                description="返回桌面",
                expected_result="回到主屏幕"
            )
            plan.confidence = 0.95
            return plan

        # 返回上一页
        if any(kw in instruction_lower for kw in ["返回", "back", "后退", "上一页"]) and "桌面" not in instruction_lower:
            plan.add_step(
                action="back",
                target=None,
                description="返回上一页",
                expected_result="返回上一个界面"
            )
            plan.confidence = 0.95
            return plan

        # 滑动操作
        if any(kw in instruction_lower for kw in ["滑动", "swipe", "scroll", "翻页"]):
            direction = self._extract_direction(instruction)
            plan.add_step(
                action="swipe",
                target=None,
                parameters={"direction": direction},
                description=f"向{direction}滑动",
                expected_result="屏幕滚动"
            )
            plan.confidence = 0.9
            return plan

        # 截图
        if any(kw in instruction_lower for kw in ["截图", "screenshot", "截屏"]):
            plan.add_step(
                action="screenshot",
                target=None,
                description="截取屏幕",
                expected_result="截图保存"
            )
            plan.confidence = 0.95
            return plan

        # 打开应用
        if any(kw in instruction_lower for kw in ["打开", "open", "启动", "launch"]):
            app_name = self._extract_app_name(instruction)
            plan.add_step(
                action="home",
                target=None,
                description="先返回桌面"
            )
            plan.add_step(
                action="tap",
                target=app_name,
                description=f"点击{app_name}",
                expected_result=f"{app_name}应该被打开"
            )
            plan.confidence = 0.8
            return plan

        # 点击操作
        if any(kw in instruction_lower for kw in ["点击", "click", "tap", "按"]):
            target = self._extract_target(instruction)
            plan.add_step(
                action="tap",
                target=target,
                description=f"点击{target}",
                expected_result="元素被点击"
            )
            plan.confidence = 0.8
            return plan

        # 输入文本
        if any(kw in instruction_lower for kw in ["输入", "input", "type", "写"]):
            text = self._extract_text_to_input(instruction)
            plan.add_step(
                action="input",
                target=None,
                parameters={"text": text},
                description=f"输入: {text}",
                expected_result="文本已输入"
            )
            plan.confidence = 0.8
            return plan

        # 发送
        if any(kw in instruction_lower for kw in ["发送", "send"]):
            plan.add_step(
                action="tap",
                target="发送",
                description="点击发送按钮",
                expected_result="消息已发送"
            )
            plan.confidence = 0.8
            return plan

        # 无法识别的指令，低置信度
        plan.add_step(
            action="tap",
            target=instruction,
            description=f"执行: {instruction}",
            expected_result="操作完成"
        )
        plan.confidence = 0.3  # 低置信度，会触发LLM调用

        return plan

    def _extract_app_name(self, instruction: str) -> str:
        """Extract app name from instruction."""
        keywords = ["打开", "open", "启动", "launch"]
        for kw in keywords:
            if kw in instruction.lower():
                parts = instruction.lower().split(kw)
                if len(parts) > 1:
                    return parts[1].strip().split()[0] if parts[1].strip() else "app"
        return "app"

    def _extract_target(self, instruction: str) -> str:
        """Extract target element from instruction."""
        keywords = ["点击", "click", "tap", "按"]
        for kw in keywords:
            if kw in instruction.lower():
                parts = instruction.lower().split(kw)
                if len(parts) > 1:
                    return parts[1].strip().split()[0] if parts[1].strip() else "element"
        return "element"

    def _extract_text_to_input(self, instruction: str) -> str:
        """Extract text to input from instruction."""
        import re
        # Look for text in quotes
        quoted = re.findall(r'["\'](.+?)["\']', instruction)
        if quoted:
            return quoted[0]

        # Look for text after colon
        if "：" in instruction:
            return instruction.split("：")[-1].strip()
        if ":" in instruction:
            return instruction.split(":")[-1].strip()

        return "text"

    def _extract_direction(self, instruction: str) -> str:
        """Extract swipe direction from instruction."""
        if "上" in instruction or "up" in instruction.lower():
            return "up"
        if "下" in instruction or "down" in instruction.lower():
            return "down"
        if "左" in instruction or "left" in instruction.lower():
            return "left"
        if "右" in instruction or "right" in instruction.lower():
            return "right"
        return "down"
