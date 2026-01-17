"""Modular Orchestrator - 模块化任务编排器

使用动态规划模式执行任务：
1. 获取当前UI状态
2. 结合总任务 + 已完成步骤 → 规划下一步
3. 执行下一步
4. 记录结果
5. 重复直到完成
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from mobile_use.domain.services.agents.dynamic_planner import (
    DynamicTaskPlanner,
    UIContext,
    CompletedStep,
    NextStep,
    PlanningResult,
    TaskStatus,
)


class ExecutionState(Enum):
    """执行状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StepResult:
    """单步执行结果"""
    success: bool
    action: str
    target: str | None = None
    description: str = ""
    error: str | None = None
    duration_ms: int = 0


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    task: str
    steps_executed: int = 0
    duration_ms: int = 0
    completed_steps: list[CompletedStep] = field(default_factory=list)
    error: str | None = None
    state: ExecutionState = ExecutionState.COMPLETED


# 进度回调类型
ProgressCallback = Callable[[int, int, str, str, str], None]


class ModularOrchestrator:
    """模块化任务编排器
    
    职责：
    1. 协调动态规划器和动作执行器
    2. 管理任务执行流程
    3. 跟踪执行进度
    4. 处理错误和重试
    """
    
    def __init__(
        self,
        planner: DynamicTaskPlanner,
        action_executor: Any,  # ActionExecutorAgent
        device_controller: Any,  # AndroidController
        max_steps: int = 10,
        step_timeout_ms: int = 30000
    ):
        self.planner = planner
        self.action_executor = action_executor
        self.device_controller = device_controller
        self.max_steps = max_steps
        self.step_timeout_ms = step_timeout_ms
        
        self.state = ExecutionState.IDLE
        self.on_progress: ProgressCallback | None = None
        self.stop_check: Callable[[], bool] | None = None  # 停止检查回调
    
    async def execute_task(self, task: str) -> TaskResult:
        """执行任务
        
        Args:
            task: 任务描述
            
        Returns:
            TaskResult: 执行结果
        """
        start_time = datetime.now()
        self.state = ExecutionState.RUNNING
        
        completed_steps: list[CompletedStep] = []
        step_count = 0
        
        print(f"\n{'='*50}")
        print(f"[Orchestrator] 开始任务: {task}")
        print(f"{'='*50}\n")
        
        try:
            while step_count < self.max_steps:
                # 检查是否请求停止
                if self.stop_check and self.stop_check():
                    print(f"[Orchestrator] 收到停止请求，任务终止")
                    self.state = ExecutionState.FAILED
                    return TaskResult(
                        success=False,
                        task=task,
                        steps_executed=len(completed_steps),
                        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                        completed_steps=completed_steps,
                        error="用户停止了任务",
                        state=ExecutionState.FAILED
                    )
                
                step_count += 1
                print(f"\n--- 步骤 {step_count}/{self.max_steps} ---")
                
                # 1. 获取当前UI状态
                ui_context = await self._get_ui_context()
                print(f"[Step {step_count}] 获取到 {len(ui_context.elements)} 个UI元素")
                
                # 2. 规划下一步
                print(f"[Step {step_count}] 规划下一步...")
                plan_result = await self.planner.plan_next_step(
                    task=task,
                    ui_context=ui_context,
                    completed_steps=completed_steps
                )
                
                # 3. 检查是否完成
                if plan_result.task_complete:
                    print(f"[Step {step_count}] 任务完成: {plan_result.reason}")
                    self.state = ExecutionState.COMPLETED
                    break
                
                # 获取所有待执行的步骤（支持批量操作）
                all_steps = plan_result.get_all_steps()
                
                if not all_steps:
                    # 检查是否是 LLM 调用失败（如速率限制）
                    if plan_result.confidence == 0.0:
                        print(f"[Step {step_count}] LLM调用失败: {plan_result.reason}")
                        print(f"[Step {step_count}] 等待5秒后重试...")
                        await asyncio.sleep(5)  # 等待5秒后重试
                        continue
                    print(f"[Step {step_count}] 无法规划下一步")
                    continue
                
                # 如果是批量操作，打印提示
                if plan_result.has_batch_steps():
                    print(f"[Step {step_count}] 批量操作: 共 {len(all_steps)} 个步骤")
                    
                    # 智能转换：如果是批量click数字，但页面有输入框，自动转换为input
                    if self._should_convert_clicks_to_input(all_steps, ui_context):
                        combined_text = self._extract_digits_from_clicks(all_steps)
                        if combined_text:
                            print(f"[Step {step_count}] 智能转换: 批量click -> input '{combined_text}' (检测到输入框)")
                            # 替换为单个 input 操作
                            from mobile_use.domain.services.agents.dynamic_planner import NextStep
                            all_steps = [NextStep(
                                action="input",
                                target=None,
                                target_index=None,
                                parameters={"text": combined_text},
                                description=f"输入 {combined_text}"
                            )]
                
                # 智能转换：如果上一步点击了输入框，当前是批量click数字，转换为input
                if completed_steps and self._last_step_clicked_input(completed_steps):
                    if self._is_digit_clicks(all_steps):
                        combined_text = self._extract_digits_from_clicks(all_steps)
                        if combined_text:
                            print(f"[Step {step_count}] 智能转换: click -> input '{combined_text}' (上一步点击了输入框)")
                            from mobile_use.domain.services.agents.dynamic_planner import NextStep
                            all_steps = [NextStep(
                                action="input",
                                target=None,
                                target_index=None,
                                parameters={"text": combined_text},
                                description=f"输入 {combined_text}"
                            )]
                
                # 检测滑动卡住，自动修正方向
                for next_step in all_steps:
                    if next_step.action == "scroll":
                        reverse_dir = self._check_scroll_stuck(completed_steps)
                        if reverse_dir:
                            original_dir = next_step.parameters.get("direction", "")
                            # 如果 LLM 还是要往卡住的方向滑，自动修正为反向
                            if original_dir != reverse_dir:
                                print(f"[Step {step_count}] 自动修正: 滑动方向 {original_dir} -> {reverse_dir} (检测到边界)")
                                next_step.parameters["direction"] = reverse_dir
                
                # 执行所有步骤
                for step_idx, next_step in enumerate(all_steps):
                    if plan_result.has_batch_steps():
                        print(f"[Step {step_count}.{step_idx + 1}] 执行: {next_step.description}")
                    
                    # 如果使用了 target_index，根据编号获取元素并设置 target
                    if next_step.target_index is not None and next_step.action in ("tap", "click"):
                        # 1. 获取编号对应的元素
                        element = ui_context.get_element_by_index(next_step.target_index)
                        
                        if element:
                            # 获取元素名称和坐标
                            elem_name = element.get('text') or element.get('content_desc') or f"元素{next_step.target_index}"
                            center = element.get('center', (0, 0))
                            
                            # 2. 验证编号是否正确：从description中提取目标名称
                            target_name_from_desc = None
                            if next_step.description and '：' in next_step.description:
                                # 尝试提取"点击第X个元素：名称"中的"名称"
                                parts = next_step.description.split('：', 1)
                                if len(parts) == 2:
                                    target_name_from_desc = parts[1].strip()
                            
                            # 3. 如果描述中的名称与实际元素名称不匹配，尝试修正
                            if target_name_from_desc and target_name_from_desc not in elem_name:
                                print(f"[Step {step_count}] ⚠️ 检测到编号错误: 描述说'{target_name_from_desc}'，但编号[{next_step.target_index}]是'{elem_name}'")
                                
                                # 尝试在元素列表中查找匹配的元素
                                all_indexed = ui_context.get_indexed_all_elements()
                                matched_element = None
                                matched_index = None
                                best_match_score = 0
                                
                                # 清理目标名称（去除标点、空格、前缀）
                                target_cleaned = target_name_from_desc.replace(':', '').replace('：', '').replace(' ', '').lower()
                                # 提取关键词（去除常见前缀如"单曲"、"歌曲"等）
                                target_keywords = target_cleaned
                                for prefix in ['单曲', '歌曲', '专辑', '视频', '音乐']:
                                    if target_keywords.startswith(prefix):
                                        target_keywords = target_keywords[len(prefix):]
                                        break
                                
                                # 多轮匹配：从严格到宽松
                                for idx, name, elem in all_indexed:
                                    name_cleaned = name.replace(':', '').replace('：', '').replace(' ', '').lower()
                                    
                                    # 1. 完全匹配（最高优先级）
                                    if target_name_from_desc == name or target_cleaned == name_cleaned:
                                        matched_element = elem
                                        matched_index = idx
                                        best_match_score = 100
                                        break
                                    
                                    # 2. 包含匹配（双向）
                                    if target_name_from_desc in name or name in target_name_from_desc:
                                        if best_match_score < 80:
                                            matched_element = elem
                                            matched_index = idx
                                            best_match_score = 80
                                        continue
                                    
                                    # 3. 清理后的包含匹配
                                    if target_cleaned in name_cleaned or name_cleaned in target_cleaned:
                                        if best_match_score < 70:
                                            matched_element = elem
                                            matched_index = idx
                                            best_match_score = 70
                                        continue
                                    
                                    # 4. 关键词匹配
                                    if target_keywords and len(target_keywords) > 1:
                                        if target_keywords in name_cleaned or name_cleaned in target_keywords:
                                            if best_match_score < 60:
                                                matched_element = elem
                                                matched_index = idx
                                                best_match_score = 60
                                            continue
                                
                                # 如果找到匹配，输出日志
                                if matched_element and best_match_score >= 60:
                                    # 从all_indexed中获取匹配元素的名称
                                    matched_name = ""
                                    for idx, name, _ in all_indexed:
                                        if idx == matched_index:
                                            matched_name = name
                                            break
                                    print(f"[Step {step_count}] ✓ 自动修正: 编号 [{next_step.target_index}] -> [{matched_index}] ('{matched_name}', 匹配度:{best_match_score})")
                                else:
                                    matched_element = None
                                    matched_index = None
                                
                                # 如果找到匹配的元素，使用它
                                if matched_element:
                                    element = matched_element
                                    next_step.target_index = matched_index
                                    elem_name = element.get('text') or element.get('content_desc') or f"元素{matched_index}"
                                    center = element.get('center', (0, 0))
                                else:
                                    print(f"[Step {step_count}] ⚠️ 无法找到匹配元素，将使用原编号")
                            
                            if not plan_result.has_batch_steps():
                                print(f"[Step {step_count}] 下一步: [{next_step.action}] {next_step.description}")
                            print(f"[Step {step_count}] 使用编号 [{next_step.target_index}] -> {elem_name}, 坐标: {center}")
                            
                            # 将坐标存入 parameters 供 ActionExecutor 使用
                            next_step.parameters['x'] = center[0]
                            next_step.parameters['y'] = center[1]
                            next_step.target = elem_name  # 同时设置 target 用于日志
                        else:
                            print(f"[Step {step_count}] 警告: 编号 [{next_step.target_index}] 无效，元素不存在")
                    elif next_step.action in ("tap", "click") and 'x' in next_step.parameters and 'y' in next_step.parameters:
                        # LLM 直接指定了坐标（用于浮层/弹窗等无法识别的元素）
                        x, y = next_step.parameters['x'], next_step.parameters['y']
                        if not plan_result.has_batch_steps():
                            print(f"[Step {step_count}] 下一步: [{next_step.action}] {next_step.description}")
                        print(f"[Step {step_count}] 使用直接坐标: ({x}, {y})")
                    elif not plan_result.has_batch_steps():
                        print(f"[Step {step_count}] 下一步: [{next_step.action}] {next_step.description}")

                    # 4. 通知进度
                    if self.on_progress:
                        self.on_progress(
                            len(completed_steps),
                            len(completed_steps) + 1,
                            next_step.action,
                            next_step.description,
                            next_step.target or ""
                        )

                    # 5. 记录执行前的UI元素（批量操作只在第一步记录）
                    if step_idx == 0:
                        ui_before = ui_context.get_all_elements()

                    # 6. 执行动作
                    step_result = await self._execute_step(next_step, ui_context)
                    
                    # 7. 批量操作之间短暂等待，单步操作正常等待
                    if plan_result.has_batch_steps():
                        await asyncio.sleep(0.1)  # 批量操作间隔短
                    else:
                        await asyncio.sleep(0.5)  # 单步操作等待UI更新
                    
                    # 8. 记录结果
                    completed_step = CompletedStep(
                        action=next_step.action,
                        target=next_step.target,
                        description=next_step.description,
                        success=step_result.success,
                        error=step_result.error if not step_result.success else None,
                        parameters=next_step.parameters,
                        ui_before=ui_before[:20] if step_idx == 0 else [],
                        ui_after=[],  # 批量操作中间不检测UI变化
                        ui_changed=False
                    )
                    completed_steps.append(completed_step)
                    
                    if not step_result.success:
                        print(f"[Step {step_count}] 执行失败: {step_result.error}")
                        if plan_result.has_batch_steps():
                            print(f"[Step {step_count}] 批量操作中断")
                            break  # 批量操作中有失败则中断
                
                # 批量操作完成后，获取最终UI状态
                await asyncio.sleep(0.3)
                ui_after_context = await self._get_ui_context()
                ui_after = ui_after_context.get_all_elements()
                ui_changed = set(ui_before) != set(ui_after)
                
                # 更新最后一个步骤的UI信息
                if completed_steps:
                    completed_steps[-1].ui_after = ui_after[:20]
                    completed_steps[-1].ui_changed = ui_changed
                
                if ui_changed:
                    print(f"[Step {step_count}] 执行成功，UI已更新")
                else:
                    print(f"[Step {step_count}] 执行成功，但UI未变化")
                
                # 10. 检测连续失败，超过3次则停止任务（保持当前界面，不执行home）
                consecutive_failures = self._count_consecutive_failures(completed_steps)
                if consecutive_failures >= 3:
                    failure_reasons = self._get_failure_reasons(completed_steps, 3)
                    error_msg = f"连续{consecutive_failures}次操作失败，任务终止。失败原因: {failure_reasons}"
                    print(f"[Orchestrator] {error_msg}")
                    self.state = ExecutionState.FAILED
                    return TaskResult(
                        success=False,
                        task=task,
                        steps_executed=len(completed_steps),
                        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                        completed_steps=completed_steps,
                        error=error_msg,
                        state=ExecutionState.FAILED
                    )
                
                # 11. 检测连续无效操作（UI未变化），只打印警告，不终止执行
                consecutive_no_change = self._count_consecutive_no_change(completed_steps)
                if consecutive_no_change >= 3:
                    print(f"[Orchestrator] 警告: 连续{consecutive_no_change}次操作后页面无变化，继续尝试...")
            
            else:
                # 达到最大步数
                print(f"[Orchestrator] 达到最大步数限制 ({self.max_steps})")
                self.state = ExecutionState.FAILED
                return TaskResult(
                    success=False,
                    task=task,
                    steps_executed=len(completed_steps),
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    completed_steps=completed_steps,
                    error=f"达到最大步数限制 ({self.max_steps})",
                    state=ExecutionState.FAILED
                )
            
            # 任务完成
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            print(f"\n{'='*50}")
            print(f"[Orchestrator] 任务完成，共 {len(completed_steps)} 步，耗时 {duration_ms}ms")
            print(f"{'='*50}\n")
            
            return TaskResult(
                success=True,
                task=task,
                steps_executed=len(completed_steps),
                duration_ms=duration_ms,
                completed_steps=completed_steps,
                state=ExecutionState.COMPLETED
            )
            
        except Exception as e:
            print(f"[Orchestrator] 执行异常: {e}")
            self.state = ExecutionState.FAILED
            return TaskResult(
                success=False,
                task=task,
                steps_executed=len(completed_steps),
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                completed_steps=completed_steps,
                error=str(e),
                state=ExecutionState.FAILED
            )
    
    async def _get_ui_context(self) -> UIContext:
        """获取当前UI上下文"""
        elements = []
        screenshot = None
        
        if self.device_controller:
            try:
                elements = await self.device_controller.get_ui_hierarchy()
            except Exception as e:
                print(f"[Orchestrator] 获取UI元素失败: {e}")
            
            try:
                result = await self.device_controller.take_screenshot()
                if result.success:
                    screenshot = result.data.get("screenshot")
                    # 压缩截图以加快API调用
                    if screenshot:
                        screenshot = self._compress_screenshot(screenshot)
            except Exception as e:
                print(f"[Orchestrator] 获取截图失败: {e}")
        
        return UIContext(elements=elements, screenshot=screenshot)
    
    def _compress_screenshot(self, screenshot: bytes, max_size_kb: int = 200) -> bytes:
        """压缩截图到指定大小以加快API调用"""
        try:
            from PIL import Image
            import io
            
            original_size = len(screenshot) / 1024
            if original_size <= max_size_kb:
                print(f"[Orchestrator] 截图大小: {original_size:.1f}KB，无需压缩")
                return screenshot
            
            img = Image.open(io.BytesIO(screenshot))
            
            # 缩小尺寸
            width, height = img.size
            scale = 0.5  # 缩小到50%
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 转为JPEG并压缩
            output = io.BytesIO()
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img.save(output, format='JPEG', quality=70, optimize=True)
            compressed = output.getvalue()
            
            new_size_kb = len(compressed) / 1024
            print(f"[Orchestrator] 截图压缩: {original_size:.1f}KB -> {new_size_kb:.1f}KB")
            return compressed
        except Exception as e:
            print(f"[Orchestrator] 截图压缩失败: {e}，使用原图")
            return screenshot
    
    async def _execute_step(self, step: NextStep, ui_context: UIContext) -> StepResult:
        """执行单个步骤"""
        start_time = datetime.now()
        
        try:
            # 构建执行上下文
            from mobile_use.domain.services.agents.base import AgentContext
            import uuid
            
            context = AgentContext(
                task_id=str(uuid.uuid4()),
                instruction=step.description,
                ui_elements=ui_context.elements,
                screenshot=ui_context.screenshot
            )
            context.metadata["plan"] = {
                "steps": [step.to_dict()]
            }
            context.current_step = 0
            
            # 执行动作
            result = await asyncio.wait_for(
                self.action_executor.execute(context),
                timeout=self.step_timeout_ms / 1000
            )
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return StepResult(
                success=result.success,
                action=step.action,
                target=step.target,
                description=step.description,
                error=result.error if not result.success else None,
                duration_ms=duration_ms
            )
            
        except asyncio.TimeoutError:
            return StepResult(
                success=False,
                action=step.action,
                target=step.target,
                description=step.description,
                error="执行超时",
                duration_ms=self.step_timeout_ms
            )
        except Exception as e:
            return StepResult(
                success=False,
                action=step.action,
                target=step.target,
                description=step.description,
                error=str(e),
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000)
            )
    
    def _count_consecutive_failures(self, completed_steps: list[CompletedStep]) -> int:
        """统计连续失败次数"""
        count = 0
        for step in reversed(completed_steps):
            if not step.success:
                count += 1
            else:
                break
        return count
    
    def _count_consecutive_no_change(self, completed_steps: list[CompletedStep]) -> int:
        """统计连续UI未变化次数"""
        count = 0
        for step in reversed(completed_steps):
            if step.success and not step.ui_changed:
                count += 1
            else:
                break
        return count
    
    def _get_failure_reasons(self, completed_steps: list[CompletedStep], count: int) -> str:
        """获取最近N次失败的原因"""
        failures = []
        for step in reversed(completed_steps):
            if not step.success and len(failures) < count:
                reason = f"[{step.action}] {step.error or '未知错误'}"
                if step.target:
                    reason = f"[{step.action}:{step.target}] {step.error or '未知错误'}"
                failures.append(reason)
            if len(failures) >= count:
                break
        return "; ".join(reversed(failures))
    
    def _check_scroll_stuck(self, completed_steps: list[CompletedStep]) -> str | None:
        """检测是否连续滑动卡住，返回应该使用的反向方向"""
        if len(completed_steps) < 2:
            return None
        
        # 检查最近2次是否都是滑动且UI无变化
        recent = completed_steps[-2:]
        scroll_no_change = []
        
        for step in recent:
            if step.action == "scroll" and step.success and not step.ui_changed:
                direction = step.parameters.get("direction", "")
                scroll_no_change.append(direction)
        
        # 如果连续2次相同方向滑动都无变化，返回反向
        if len(scroll_no_change) >= 2 and scroll_no_change[-1] == scroll_no_change[-2]:
            direction = scroll_no_change[-1]
            return self._get_opposite_direction(direction)
        
        return None
    
    def _get_opposite_direction(self, direction: str) -> str:
        """获取反向方向"""
        reverse_map = {
            "up": "down",
            "down": "up",
            "left": "right",
            "right": "left"
        }
        return reverse_map.get(direction, direction)
    
    def _should_convert_clicks_to_input(self, steps: list, ui_context: UIContext) -> bool:
        """判断是否应该将批量click转换为input（当有输入框时）"""
        # 检查是否全是click/tap数字的操作
        digit_pattern = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '。']
        is_digit_clicks = True
        for step in steps:
            if step.action not in ("click", "tap"):
                is_digit_clicks = False
                break
            # 检查描述中是否包含数字
            desc = step.description or ""
            has_digit = any(d in desc for d in digit_pattern)
            if not has_digit:
                is_digit_clicks = False
                break
        
        if not is_digit_clicks:
            return False
        
        # 检查页面是否有输入框
        for elem in ui_context.elements:
            class_name = (elem.get('class_name') or elem.get('class') or '').lower()
            if 'edittext' in class_name or 'input' in class_name:
                return True
        
        return False
    
    def _extract_digits_from_clicks(self, steps: list) -> str:
        """从批量click操作中提取数字组成字符串"""
        digits = []
        for step in steps:
            desc = step.description or ""
            # 从描述中提取数字，如 "点击数字1" -> "1"
            for char in desc:
                if char in '0123456789.':
                    digits.append(char)
                    break  # 每个步骤只取一个数字
        return ''.join(digits)
    
    def _last_step_clicked_input(self, completed_steps: list[CompletedStep]) -> bool:
        """检查上一步是否点击了输入框"""
        if not completed_steps:
            return False
        last_step = completed_steps[-1]
        if last_step.action not in ("tap", "click"):
            return False
        # 检查目标是否是输入框
        target = (last_step.target or "").lower()
        if "输入" in target or "input" in target or "edit" in target or "搜索" in target:
            return True
        # 检查描述
        desc = (last_step.description or "").lower()
        if "输入框" in desc or "搜索框" in desc or "edittext" in desc:
            return True
        return False
    
    def _is_digit_clicks(self, steps: list) -> bool:
        """检查是否全是点击数字的操作（排除元素编号）"""
        if not steps:
            return False
        
        for step in steps:
            if step.action not in ("click", "tap"):
                return False
            
            desc = (step.description or "").lower()
            
            # ❌ 排除：包含"第X个元素"、"编号"等描述（这是元素索引，不是数字键盘）
            if "第" in desc and "元素" in desc:
                return False
            if "编号" in desc:
                return False
            
            # ✅ 必须明确是点击数字按钮
            digit_keywords = ["点击数字", "数字键", "按键", "密码", "pin"]
            has_digit_keyword = any(kw in desc for kw in digit_keywords)
            
            # 检查是否有单独的数字（0-9）
            digit_pattern = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
            single_digits = [d for d in digit_pattern if d in desc]
            
            # 必须同时满足：有数字关键词 或 描述非常简短只有数字
            if not (has_digit_keyword or (len(desc) <= 10 and single_digits)):
                return False
        
        return True
