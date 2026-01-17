"""Action Executor Agent - Executes device actions."""

from typing import Any, Protocol

from mobile_use.domain.services.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
)
from mobile_use.domain.value_objects.point import Point


class DeviceControllerProtocol(Protocol):
    """Protocol for device controllers."""
    async def tap(self, point: Point) -> Any:
        """Tap at point."""
        ...

    async def swipe(self, start: Point, end: Point, duration_ms: int = 500) -> Any:
        """Swipe from start to end."""
        ...

    async def input_text(self, text: str) -> Any:
        """Input text."""
        ...

    async def press_key(self, key: str) -> Any:
        """Press a key."""
        ...

    async def take_screenshot(self, save_path: str | None = None) -> Any:
        """Take screenshot."""
        ...


class ActionExecutorAgent(BaseAgent):
    """Agent responsible for executing device actions.

    This agent takes planned actions and executes them on the device,
    handling the low-level interaction with the device controller.
    """

    def __init__(self, device_controller: DeviceControllerProtocol | None = None, llm_provider: Any = None):
        super().__init__(
            name="ActionExecutor",
            description="Executes device actions based on planned steps"
        )
        self.device_controller = device_controller
        self.llm_provider = llm_provider
        self.default_action_delay_ms = 500
        self.max_recovery_attempts = 3  # 最大恢复尝试次数
        self.recovery_history: list[dict] = []  # 恢复操作历史
        self.obstacle_check_count = 0  # 障碍物检测次数
        self.max_obstacle_checks = 2  # 每个步骤最多检测2次障碍物
        
        # 需要忽略的系统元素（如ATX悬浮窗）
        self.ignore_elements = [
            "atx", "uiautomator", "floating", "悬浮"
        ]
        
        # 障碍物检测现在主要依赖LLM+截图，不再使用固定关键词
        
        # 可用的恢复策略
        self.recovery_strategies = [
            "scroll_down",      # 向下滚动寻找目标
            "scroll_up",        # 向上滚动寻找目标
            "swipe_left",       # 向左滑动（切换tab等）
            "swipe_right",      # 向右滑动
            "go_back",          # 返回上一页
            "close_popup",      # 关闭弹窗
            "tap_alternative",  # 点击替代元素
            "wait_and_retry",   # 等待后重试
            "llm_decide",       # 让LLM决定
        ]

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute planned actions.

        Args:
            context: Current execution context with action plan

        Returns:
            AgentResult containing execution results
        """
        if not self.device_controller:
            return AgentResult.failure_result(
                error="No device controller available",
                message="Cannot execute actions without device controller"
            )

        # Get current step from context
        plan = context.metadata.get("plan", {})
        steps = plan.get("steps", [])

        if not steps:
            return AgentResult.failure_result(
                error="No steps to execute",
                message="No action plan found in context"
            )

        current_step_index = context.current_step
        if current_step_index >= len(steps):
            return AgentResult.success_result(
                message="All steps completed",
                data={"completed": True}
            )

        step = steps[current_step_index]
        action = step.get("action", "")
        target = step.get("target")
        parameters = step.get("parameters", {})
        
        print(f"[ActionExecutor] ========== 执行步骤 {current_step_index + 1}/{len(steps)} ==========")
        print(f"[ActionExecutor] 动作: {action}, 目标: {target}, 参数: {parameters}")

        # 暂时禁用障碍物检测模块
        # TODO: 后续优化后再启用
        # if context.ui_elements and self.llm_provider and self.obstacle_check_count < self.max_obstacle_checks:
        #     self.obstacle_check_count += 1
        #     handled = await self._handle_obstacles(context.ui_elements, context)
        #     if handled:
        #         print(f"[ActionExecutor] 已处理障碍物（第{self.obstacle_check_count}次），需要刷新UI后重试")
        handled = False
        if handled:
                # 返回需要重新获取UI的信号
                return AgentResult.success_result(
                    message="Handled obstacle, need to refresh UI",
                    data={
                        "step_index": current_step_index,
                        "obstacle_handled": True,
                        "retry_step": True,  # 标记需要重试当前步骤
                        "next_step": current_step_index  # 保持当前步骤
                    },
                    next_step="analyze"  # 回到分析阶段刷新UI
                )

        # Execute the action
        try:
            result = await self._execute_action(
                action=action,
                target=target,
                parameters=parameters,
                context=context
            )

            # 检查是否需要自主恢复
            if not result.get("success") and result.get("needs_recovery"):
                print(f"[ActionExecutor] 动作执行失败，启动自主恢复...")
                recovery_result = await self._autonomous_recovery(
                    failed_action=action,
                    failed_target=target,
                    context=context,
                    step=step
                )
                
                if recovery_result.get("recovered"):
                    # 恢复成功，返回需要重试的信号
                    return AgentResult.success_result(
                        message=f"Recovery action taken: {recovery_result.get('action_taken')}",
                        data={
                            "step_index": current_step_index,
                            "recovery_performed": True,
                            "recovery_action": recovery_result.get("action_taken"),
                            "retry_step": True,
                            "next_step": current_step_index
                        },
                        next_step="analyze"  # 回到分析阶段刷新UI后重试
                    )
                else:
                    # 恢复失败
                    return AgentResult.failure_result(
                        error=result.get("error", "Unknown error"),
                        message=f"Failed to execute and recover: {action} (step {current_step_index}, recovery failed)"
                    )

            # 动作成功执行，重置障碍物检测计数
            self.obstacle_check_count = 0
            
            # 每个操作后短暂等待页面响应
            import asyncio
            wait_time = 0.3  # 统一短暂等待
            await asyncio.sleep(wait_time)
            
            return AgentResult.success_result(
                message=f"Executed action: {action}",
                actions=[{
                    "action": action,
                    "target": target,
                    "parameters": parameters,
                    "result": result
                }],
                data={
                    "step_index": current_step_index,
                    "action_result": result,
                    "next_step": current_step_index + 1
                },
                next_step="validate"
            )

        except Exception as e:
            return AgentResult.failure_result(
                error=str(e),
                message=f"Failed to execute action: {action}"
            )

    async def _execute_action(
        self,
        action: str,
        target: str | None,
        parameters: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Execute a single action."""
        result: dict[str, Any] = {"success": False}

        if action == "tap" or action == "click":  # click 是 tap 的别名
            result = await self._execute_tap(target, parameters, context)
        elif action == "swipe":
            result = await self._execute_swipe(parameters, context)
        elif action == "input":
            result = await self._execute_input(parameters, target)
        elif action == "wait":
            result = await self._execute_wait(parameters)
        elif action == "scroll":
            result = await self._execute_scroll(parameters, context)
        elif action == "back":
            result = await self._execute_back()
        elif action == "home":
            result = await self._execute_home()
        elif action == "press_key":
            result = await self._execute_press_key(parameters)
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}

        return result

    async def _execute_tap(
        self,
        target: str | None,
        parameters: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Execute tap action."""
        point: Point | None = None

        # Try to get coordinates from parameters
        if "x" in parameters and "y" in parameters:
            point = Point(int(parameters["x"]), int(parameters["y"]))

        # Try to find element by target text (使用异步版本支持LLM)
        elif target and context.ui_elements:
            element = await self._find_element_by_target_async(target, context.ui_elements)
            if element and element.get("center"):
                center = element["center"]
                point = Point(center[0], center[1])
                print(f"[ActionExecutor] 找到元素: {element.get('text') or element.get('content_desc')}, 坐标: {center}")

        if not point:
            # 找不到目标，触发自主恢复
            return {
                "success": False, 
                "error": f"Could not find target: {target}",
                "needs_recovery": True,
                "target": target
            }

        action_result = await self.device_controller.tap(point)  # type: ignore
        return {
            "success": True,
            "point": {"x": point.x, "y": point.y},
            "device_result": action_result
        }

    async def _execute_swipe(
        self,
        parameters: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Execute swipe action."""
        screen_info = context.screen_info or {}
        width = screen_info.get("width", 1080)
        height = screen_info.get("height", 1920)

        direction = parameters.get("direction", "down")
        duration = parameters.get("duration_ms", 500)

        center_x = width // 2
        center_y = height // 2

        if direction == "up":
            start = Point(center_x, int(height * 0.7))
            end = Point(center_x, int(height * 0.3))
        elif direction == "down":
            start = Point(center_x, int(height * 0.3))
            end = Point(center_x, int(height * 0.7))
        elif direction == "left":
            start = Point(int(width * 0.8), center_y)
            end = Point(int(width * 0.2), center_y)
        elif direction == "right":
            start = Point(int(width * 0.2), center_y)
            end = Point(int(width * 0.8), center_y)
        else:
            return {"success": False, "error": f"Unknown direction: {direction}"}

        action_result = await self.device_controller.swipe(start, end, duration)  # type: ignore
        return {
            "success": True,
            "direction": direction,
            "start": {"x": start.x, "y": start.y},
            "end": {"x": end.x, "y": end.y},
            "device_result": action_result
        }

    async def _execute_input(self, parameters: dict[str, Any], target: str | None = None) -> dict[str, Any]:
        """Execute text input action."""
        # 尝试从多个来源获取文本
        text = parameters.get("text", "") or parameters.get("content", "") or ""
        
        print(f"[ActionExecutor] 执行输入: text='{text}', target='{target}', parameters={parameters}")
        
        if not text:
            print(f"[ActionExecutor] 输入失败: 没有提供文本内容")
            return {
                "success": False, 
                "error": "No text provided in parameters",
                "needs_recovery": True  # 需要恢复，可能是计划生成问题
            }

        action_result = await self.device_controller.input_text(text)  # type: ignore
        print(f"[ActionExecutor] 输入成功: '{text}'")
        return {
            "success": True,
            "text": text,
            "device_result": action_result
        }

    async def _execute_wait(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute wait action."""
        import asyncio

        duration_ms = parameters.get("duration_ms", 1000)
        await asyncio.sleep(duration_ms / 1000)
        return {"success": True, "waited_ms": duration_ms}

    async def _execute_scroll(
        self,
        parameters: dict[str, Any],
        context: AgentContext
    ) -> dict[str, Any]:
        """Execute scroll action (alias for swipe)."""
        direction = parameters.get("direction", "down")
        return await self._execute_swipe({"direction": direction}, context)

    async def _execute_back(self) -> dict[str, Any]:
        """Execute back button press."""
        action_result = await self.device_controller.press_key("BACK")  # type: ignore
        return {"success": True, "key": "BACK", "device_result": action_result}

    async def _execute_home(self) -> dict[str, Any]:
        """Execute home button press."""
        action_result = await self.device_controller.press_key("HOME")  # type: ignore
        return {"success": True, "key": "HOME", "device_result": action_result}

    async def _execute_press_key(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute key press action (ENTER, SEARCH, BACK, HOME, etc.)."""
        key = parameters.get("key", "ENTER").upper()
        # 映射常见按键到设备支持的按键
        key_map = {
            # 基础导航
            "ENTER": "ENTER",
            "BACK": "BACK",
            "HOME": "HOME",
            "MENU": "MENU",
            "RECENT": "RECENT",  # 最近任务/多任务
            "RECENTS": "RECENT",
            # 搜索
            "SEARCH": "SEARCH",
            # 音量控制
            "VOLUME_UP": "VOLUME_UP",
            "VOLUMEUP": "VOLUME_UP",
            "VOLUME_DOWN": "VOLUME_DOWN",
            "VOLUMEDOWN": "VOLUME_DOWN",
            # 电源
            "POWER": "POWER",
            # 编辑
            "TAB": "TAB",
            "DELETE": "DEL",
            "BACKSPACE": "DEL",
            "DEL": "DEL",
            # 方向键
            "UP": "UP",
            "DOWN": "DOWN",
            "LEFT": "LEFT",
            "RIGHT": "RIGHT",
            "CENTER": "CENTER",
        }
        mapped_key = key_map.get(key, key)
        action_result = await self.device_controller.press_key(mapped_key)  # type: ignore
        return {"success": True, "key": mapped_key, "device_result": action_result}

    async def _find_element_by_target_async(
        self,
        target: str,
        ui_elements: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find UI element matching target description, with LLM fallback."""
        # 先尝试精确匹配
        result = self._find_element_by_target_simple(target, ui_elements)
        if result:
            return result
        
        # 精确匹配失败，使用LLM智能选择
        if self.llm_provider and ui_elements:
            print(f"[ActionExecutor] 精确匹配失败，调用LLM智能选择元素...")
            result = await self._find_element_with_llm(target, ui_elements)
            if result:
                return result
        
        return None

    def _find_element_by_target(
        self,
        target: str,
        ui_elements: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find UI element matching target description (sync version)."""
        return self._find_element_by_target_simple(target, ui_elements)

    def _find_element_by_target_simple(
        self,
        target: str,
        ui_elements: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Find UI element using simple matching rules."""
        target_lower = target.lower()
        
        # 提取关键词（去除常见后缀如 app, icon, button 等）
        keywords = self._extract_keywords(target_lower)
        print(f"[ActionExecutor] 查找目标: {target}, 关键词: {keywords}")
        
        # 过滤掉不可点击的元素和屏幕顶部的搜索框元素（y < 150 通常是状态栏/搜索框区域）
        def is_valid_target(elem: dict) -> bool:
            # 必须可点击
            if not elem.get("clickable", False):
                return False
            # 排除搜索框区域的元素（通常在屏幕顶部）
            center = elem.get("center", (0, 0))
            if center[1] < 150:  # y坐标太小，可能是搜索框
                return False
            return True
        
        # 收集所有匹配的候选元素，然后选择最佳的
        candidates: list[tuple[dict, int, str]] = []  # (element, priority, match_type)

        for element in ui_elements:
            text = element.get("text", "") or ""
            content_desc = element.get("content_desc", "") or ""
            text_lower = text.lower()
            desc_lower = content_desc.lower()
            
            # 精确匹配 - 最高优先级
            if text and text_lower == target_lower:
                candidates.append((element, 1, f"精确匹配: {text}"))
            elif content_desc and desc_lower == target_lower:
                candidates.append((element, 1, f"精确匹配(desc): {content_desc}"))
            # 目标包含在元素文本中
            elif text and target_lower in text_lower:
                candidates.append((element, 2, f"部分匹配: {text}"))
            elif content_desc and target_lower in desc_lower:
                candidates.append((element, 2, f"部分匹配(desc): {content_desc}"))
            # 关键词匹配 - 需要匹配多个关键词才更可靠
            else:
                matched_keywords = []
                for keyword in keywords:
                    if keyword and len(keyword) >= 2:
                        if keyword in text_lower or keyword in desc_lower:
                            matched_keywords.append(keyword)
                if matched_keywords:
                    # 匹配的关键词越多，优先级越高
                    priority = 5 - min(len(matched_keywords), 3)  # 3个以上关键词优先级为2
                    candidates.append((element, priority, f"关键词匹配({len(matched_keywords)}个): {text or content_desc}"))
        
        # 按优先级排序，优先级相同时优先选择可点击且位置合理的元素
        if candidates:
            # 先按优先级排序
            candidates.sort(key=lambda x: x[1])
            
            # 在相同优先级中，优先选择有效目标
            for elem, priority, match_type in candidates:
                if is_valid_target(elem):
                    print(f"[ActionExecutor] {match_type}, 坐标: {elem.get('center')}")
                    return elem
            
            # 如果没有有效目标，返回第一个匹配（可能是搜索框等）
            elem, priority, match_type = candidates[0]
            print(f"[ActionExecutor] {match_type} (非理想目标), 坐标: {elem.get('center')}")
            return elem

        print(f"[ActionExecutor] 未找到匹配元素")
        return None

    def _extract_keywords(self, target: str) -> list[str]:
        """从目标描述中提取关键词."""
        stop_words = ["app", "icon", "button", "the", "a", "an", "click", "tap", "open", "launch", "打开", "点击", "按钮", "图标"]
        words = target.replace(",", " ").replace(".", " ").split()
        keywords = [w for w in words if w not in stop_words and len(w) >= 2]
        clean_target = "".join(target.split())
        for sw in stop_words:
            clean_target = clean_target.replace(sw, "")
        if clean_target and len(clean_target) >= 2:
            keywords.append(clean_target)
        return keywords

    def _find_by_position(self, target: str, ui_elements: list[dict[str, Any]]) -> dict[str, Any] | None:
        """根据位置描述查找元素（如第一个视频、first button）."""
        position_map = {
            "第一": 0, "first": 0, "1st": 0,
            "第二": 1, "second": 1, "2nd": 1,
            "第三": 2, "third": 2, "3rd": 2,
            "第四": 3, "fourth": 3, "4th": 3,
            "第五": 4, "fifth": 4, "5th": 4,
        }
        type_keywords = {
            "视频": ["video", "视频", "播放"],
            "图片": ["image", "图片", "photo"],
            "按钮": ["button", "按钮", "btn"],
            "链接": ["link", "链接"],
            "文本": ["text", "文字"],
            "输入": ["input", "edit", "输入框"],
        }
        position = -1
        for pos_key, pos_val in position_map.items():
            if pos_key in target:
                position = pos_val
                break
        if position < 0:
            return None
        element_type = None
        for type_name, type_kws in type_keywords.items():
            for kw in type_kws:
                if kw in target:
                    element_type = type_name
                    break
            if element_type:
                break
        print(f"[ActionExecutor] 位置查找: position={position}, type={element_type}")
        if element_type == "视频":
            clickable = [e for e in ui_elements if e.get("clickable") and e.get("center")]
            clickable.sort(key=lambda e: (e.get("center", [0, 0])[1], e.get("center", [0, 0])[0]))
            if position < len(clickable):
                elem = clickable[position]
                print(f"[ActionExecutor] 位置匹配: 第{position+1}个可点击元素")
                return elem
        else:
            clickable = [e for e in ui_elements if e.get("clickable") and e.get("center")]
            if position < len(clickable):
                return clickable[position]
        return None

    async def _handle_obstacles(self, ui_elements: list[dict[str, Any]], context: AgentContext) -> bool:
        """使用LLM+截图检测并处理障碍物。返回True表示已处理，需要刷新UI。"""
        # 没有LLM则不进行障碍物检测
        if not self.llm_provider:
            return False
        
        # 过滤掉系统元素（如ATX悬浮窗）
        filtered_elements = self._filter_system_elements(ui_elements)
        
        # 使用LLM分析截图判断是否有障碍物
        result = await self._detect_obstacle_with_llm(filtered_elements, context)
        
        if result and result.get("has_obstacle"):
            action = result.get("action")
            if action == "tap" and result.get("element_index") is not None:
                idx = result["element_index"]
                if 0 <= idx < len(filtered_elements):
                    elem = filtered_elements[idx]
                    center = elem.get("center")
                    if center:
                        point = Point(center[0], center[1])
                        print(f"[ActionExecutor] LLM检测到障碍物，点击: {elem.get('text') or elem.get('content_desc') or f'元素{idx}'}")
                        await self.device_controller.tap(point)  # type: ignore
                        import asyncio
                        await asyncio.sleep(0.5)
                        return True
            elif action == "back":
                print(f"[ActionExecutor] LLM建议返回关闭障碍物")
                await self.device_controller.press_key("BACK")  # type: ignore
                import asyncio
                await asyncio.sleep(0.5)
                return True
        
        return False
    
    def _filter_system_elements(self, ui_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """过滤掉系统元素（如ATX悬浮窗）。"""
        filtered = []
        for elem in ui_elements:
            text = (elem.get("text", "") or "").lower()
            desc = (elem.get("content_desc", "") or "").lower()
            pkg = (elem.get("package", "") or "").lower()
            combined = text + " " + desc + " " + pkg
            
            # 跳过系统元素
            is_system = any(kw in combined for kw in self.ignore_elements)
            if not is_system:
                filtered.append(elem)
        
        return filtered
    
    async def _detect_obstacle_with_llm(
        self,
        ui_elements: list[dict[str, Any]],
        context: AgentContext
    ) -> dict[str, Any] | None:
        """使用LLM分析当前页面是否有障碍物（广告、弹窗等）。"""
        import json
        
        # 获取截图
        screenshot_b64 = None
        try:
            screenshot = await self.device_controller.take_screenshot()  # type: ignore
            if screenshot and hasattr(screenshot, 'data'):
                import base64
                screenshot_b64 = base64.b64encode(screenshot.data).decode('utf-8')
        except Exception as e:
            print(f"[ActionExecutor] 获取截图失败: {e}")
        
        # 构建元素列表
        elements_info = []
        for i, elem in enumerate(ui_elements[:30]):
            text = elem.get("text", "") or ""
            desc = elem.get("content_desc", "") or ""
            clickable = elem.get("clickable", False)
            if text or desc or clickable:
                elements_info.append({
                    "index": i,
                    "text": text,
                    "desc": desc,
                    "clickable": clickable
                })
        
        # 构建prompt - 更严格的障碍物判断
        prompt = f"""判断当前手机屏幕是否有**真正的弹窗**需要关闭。

当前任务: {context.instruction}

页面元素列表:
{json.dumps(elements_info, ensure_ascii=False, indent=2)}

**什么是需要处理的障碍物：**
- 模态对话框（有明确的"关闭"、"取消"、"跳过"按钮）
- 权限请求弹窗（如"允许/拒绝"）
- 强制更新提示
- 全屏广告（有"×"关闭按钮）

**什么不是障碍物（不要处理）：**
- 桌面上的应用图标和小部件
- 页面内嵌的广告轮播/banner（这是正常内容）
- 底部导航栏
- 状态栏
- 普通的页面元素

**重要：如果当前是手机桌面，直接返回没有障碍物！**

返回JSON：
{{
    "has_obstacle": false,
    "reason": "当前是正常页面/桌面，没有弹窗"
}}

或者如果确实有弹窗：
{{
    "has_obstacle": true,
    "reason": "检测到XXX弹窗",
    "action": "tap",
    "element_index": 关闭按钮的索引
}}"""

        try:
            # 如果有截图，使用多模态
            if screenshot_b64 and hasattr(self.llm_provider, 'generate_with_image'):
                response = await self.llm_provider.generate_with_image(prompt, screenshot_b64)
            else:
                response = await self.llm_provider.generate(prompt)
            
            # 解析响应
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            
            result = json.loads(json_str)
            
            if result.get("has_obstacle"):
                print(f"[ActionExecutor] LLM检测到障碍物: {result.get('reason')}")
            
            return result
            
        except Exception as e:
            print(f"[ActionExecutor] LLM障碍物检测失败: {e}")
            return None
    
    async def _find_element_with_llm(
        self,
        target: str,
        ui_elements: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """使用LLM智能选择最匹配的元素."""
        import json
        
        # 构建元素列表描述
        elements_info = []
        for i, elem in enumerate(ui_elements[:50]):  # 限制50个元素
            text = elem.get("text", "") or ""
            desc = elem.get("content_desc", "") or ""
            class_name = elem.get("class_name", "") or ""
            clickable = elem.get("clickable", False)
            bounds = elem.get("bounds", {})
            center = elem.get("center", [0, 0])
            
            if text or desc or clickable:
                elements_info.append({
                    "index": i,
                    "text": text,
                    "content_desc": desc,
                    "class": class_name.split(".")[-1] if class_name else "",
                    "clickable": clickable,
                    "position": {"x": center[0], "y": center[1]} if center else None
                })
        
        if not elements_info:
            return None
        
        prompt = f"""你是一个UI元素选择助手。用户想要点击"{target}"。

当前页面的UI元素列表如下（JSON格式）：
{json.dumps(elements_info, ensure_ascii=False, indent=2)}

请分析这些元素，找出最符合用户意图"{target}"的元素。

规则：
1. "第一个视频"通常指页面上第一个视频内容区域，可能是一个可点击的卡片或图片
2. 视频元素通常有封面图、标题、播放量等特征
3. 优先选择clickable=true的元素
4. 考虑元素的位置（y坐标较小的在上方）

请只返回一个JSON对象，格式为：
{{"selected_index": <元素的index>, "reason": "<选择原因>"}}

如果没有合适的元素，返回：
{{"selected_index": -1, "reason": "<原因>"}}"""

        try:
            response = await self.llm_provider.generate(prompt)
            print(f"[ActionExecutor] LLM选择响应: {response[:200]}")
            
            # 解析JSON
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            
            result = json.loads(json_str)
            selected_index = result.get("selected_index", -1)
            reason = result.get("reason", "")
            
            print(f"[ActionExecutor] LLM选择: index={selected_index}, reason={reason}")
            
            if selected_index >= 0 and selected_index < len(ui_elements):
                return ui_elements[selected_index]
            
        except Exception as e:
            print(f"[ActionExecutor] LLM选择失败: {e}")
        
        return None

    # ==================== 自主恢复系统 ====================
    
    async def _autonomous_recovery(
        self,
        failed_action: str,
        failed_target: str | None,
        context: AgentContext,
        step: dict[str, Any]
    ) -> dict[str, Any]:
        """
        自主恢复系统：当动作执行失败时，AI自主决定如何恢复。
        
        恢复策略：
        1. 滚动查找 - 目标可能在屏幕外
        2. 返回重试 - 可能进入了错误页面
        3. 关闭弹窗 - 可能有遮挡
        4. 点击替代元素 - 可能有相似的可点击项
        5. 等待重试 - 页面可能还在加载
        6. LLM智能决策 - 让AI分析情况并决定
        """
        import asyncio
        
        print(f"[Recovery] 开始自主恢复，失败动作: {failed_action}, 目标: {failed_target}")
        
        # 记录恢复尝试
        recovery_attempt = {
            "failed_action": failed_action,
            "failed_target": failed_target,
            "attempts": []
        }
        
        # 获取当前恢复尝试次数
        current_attempts = len([h for h in self.recovery_history 
                               if h.get("failed_target") == failed_target])
        
        if current_attempts >= self.max_recovery_attempts:
            print(f"[Recovery] 已达到最大恢复尝试次数 ({self.max_recovery_attempts})")
            return {"recovered": False, "reason": "Max recovery attempts reached"}
        
        # 如果有LLM，让LLM决定恢复策略
        if self.llm_provider:
            result = await self._llm_decide_recovery(
                failed_action, failed_target, context, step, current_attempts
            )
            if result.get("recovered"):
                self.recovery_history.append(recovery_attempt)
                return result
        
        # 没有LLM时使用规则恢复
        result = await self._rule_based_recovery(
            failed_action, failed_target, context, current_attempts
        )
        
        self.recovery_history.append(recovery_attempt)
        return result

    async def _llm_decide_recovery(
        self,
        failed_action: str,
        failed_target: str | None,
        context: AgentContext,
        step: dict[str, Any],
        attempt_count: int
    ) -> dict[str, Any]:
        """让LLM分析当前情况并决定恢复策略。"""
        import json
        
        # 构建当前页面元素信息
        elements_info = []
        if context.ui_elements:
            for i, elem in enumerate(context.ui_elements[:40]):
                text = elem.get("text", "") or ""
                desc = elem.get("content_desc", "") or ""
                clickable = elem.get("clickable", False)
                center = elem.get("center", [0, 0])
                class_name = (elem.get("class_name", "") or "").split(".")[-1]
                
                if text or desc or clickable:
                    elements_info.append({
                        "index": i,
                        "text": text,
                        "desc": desc,
                        "class": class_name,
                        "clickable": clickable,
                        "y": center[1] if center else 0
                    })
        
        prompt = f"""你是一个移动应用自动化助手。当前执行遇到了问题，需要你决定如何恢复。

## 失败信息
- 失败动作: {failed_action}
- 目标元素: {failed_target}
- 已尝试恢复次数: {attempt_count}
- 原始步骤描述: {step.get('description', '')}

## 当前页面元素
{json.dumps(elements_info, ensure_ascii=False, indent=2)}

## 可选恢复策略
1. scroll_down - 向下滚动（目标可能在下方）
2. scroll_up - 向上滚动（目标可能在上方）
3. swipe_left - 向左滑动（可能需要切换tab或页面）
4. swipe_right - 向右滑动
5. go_back - 返回上一页（可能进入了错误页面）
6. close_popup - 关闭弹窗（如果有遮挡）
7. tap_element - 点击一个替代元素（指定index）
8. wait - 等待页面加载
9. give_up - 放弃恢复

## 分析要求
1. 分析当前页面元素，判断目标"{failed_target}"是否可能存在
2. 如果页面上有相似或相关的元素，可以选择点击它
3. 如果目标可能在屏幕外，选择滚动
4. 如果页面看起来不对，选择返回
5. 如果有弹窗遮挡，选择关闭

请返回JSON格式：
{{
    "strategy": "策略名称",
    "element_index": 如果是tap_element则填写元素index否则为null,
    "reason": "选择这个策略的原因",
    "confidence": 0.0-1.0
}}"""

        try:
            response = await self.llm_provider.generate(prompt)
            print(f"[Recovery] LLM决策响应: {response[:300]}")
            
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            
            decision = json.loads(json_str)
            strategy = decision.get("strategy", "give_up")
            element_index = decision.get("element_index")
            reason = decision.get("reason", "")
            
            print(f"[Recovery] LLM决策: {strategy}, 原因: {reason}")
            
            # 执行恢复策略
            return await self._execute_recovery_strategy(
                strategy, element_index, context, failed_target
            )
            
        except Exception as e:
            print(f"[Recovery] LLM决策失败: {e}")
            # 回退到规则恢复
            return await self._rule_based_recovery(
                failed_action, failed_target, context, attempt_count
            )

    async def _rule_based_recovery(
        self,
        failed_action: str,
        failed_target: str | None,
        context: AgentContext,
        attempt_count: int
    ) -> dict[str, Any]:
        """基于规则的恢复策略（无LLM时使用）。"""
        
        # 根据尝试次数选择不同策略
        strategies_order = [
            "scroll_down",   # 第1次：向下滚动
            "scroll_up",     # 第2次：向上滚动
            "go_back",       # 第3次：返回
        ]
        
        if attempt_count < len(strategies_order):
            strategy = strategies_order[attempt_count]
        else:
            return {"recovered": False, "reason": "All strategies exhausted"}
        
        print(f"[Recovery] 规则恢复，尝试策略: {strategy}")
        return await self._execute_recovery_strategy(strategy, None, context, failed_target)

    async def _execute_recovery_strategy(
        self,
        strategy: str,
        element_index: int | None,
        context: AgentContext,
        original_target: str | None
    ) -> dict[str, Any]:
        """执行具体的恢复策略。"""
        import asyncio
        
        screen_info = context.screen_info or {}
        width = screen_info.get("width", 1080)
        height = screen_info.get("height", 1920)
        
        try:
            if strategy == "scroll_down":
                print("[Recovery] 执行: 向下滚动")
                start = Point(width // 2, int(height * 0.7))
                end = Point(width // 2, int(height * 0.3))
                await self.device_controller.swipe(start, end, 500)  # type: ignore
                await asyncio.sleep(0.5)
                return {"recovered": True, "action_taken": "scroll_down"}
                
            elif strategy == "scroll_up":
                print("[Recovery] 执行: 向上滚动")
                start = Point(width // 2, int(height * 0.3))
                end = Point(width // 2, int(height * 0.7))
                await self.device_controller.swipe(start, end, 500)  # type: ignore
                await asyncio.sleep(0.5)
                return {"recovered": True, "action_taken": "scroll_up"}
                
            elif strategy == "swipe_left":
                print("[Recovery] 执行: 向左滑动")
                start = Point(int(width * 0.8), height // 2)
                end = Point(int(width * 0.2), height // 2)
                await self.device_controller.swipe(start, end, 300)  # type: ignore
                await asyncio.sleep(0.5)
                return {"recovered": True, "action_taken": "swipe_left"}
                
            elif strategy == "swipe_right":
                print("[Recovery] 执行: 向右滑动")
                start = Point(int(width * 0.2), height // 2)
                end = Point(int(width * 0.8), height // 2)
                await self.device_controller.swipe(start, end, 300)  # type: ignore
                await asyncio.sleep(0.5)
                return {"recovered": True, "action_taken": "swipe_right"}
                
            elif strategy == "go_back":
                print("[Recovery] 执行: 返回上一页")
                await self.device_controller.press_key("BACK")  # type: ignore
                await asyncio.sleep(0.5)
                return {"recovered": True, "action_taken": "go_back"}
                
            elif strategy == "close_popup":
                print("[Recovery] 执行: 尝试关闭弹窗")
                if context.ui_elements:
                    handled = await self._handle_obstacles(context.ui_elements)
                    if handled:
                        return {"recovered": True, "action_taken": "close_popup"}
                return {"recovered": False, "reason": "No popup found to close"}
                
            elif strategy == "tap_element" and element_index is not None:
                print(f"[Recovery] 执行: 点击替代元素 index={element_index}")
                if context.ui_elements and element_index < len(context.ui_elements):
                    elem = context.ui_elements[element_index]
                    if elem.get("center"):
                        center = elem["center"]
                        point = Point(center[0], center[1])
                        await self.device_controller.tap(point)  # type: ignore
                        await asyncio.sleep(0.3)
                        return {
                            "recovered": True, 
                            "action_taken": f"tap_element:{elem.get('text') or elem.get('content_desc')}"
                        }
                return {"recovered": False, "reason": "Invalid element index"}
                
            elif strategy == "wait":
                print("[Recovery] 执行: 等待页面加载")
                await asyncio.sleep(2)
                return {"recovered": True, "action_taken": "wait"}
                
            elif strategy == "give_up":
                print("[Recovery] 放弃恢复")
                return {"recovered": False, "reason": "LLM decided to give up"}
                
            else:
                print(f"[Recovery] 未知策略: {strategy}")
                return {"recovered": False, "reason": f"Unknown strategy: {strategy}"}
                
        except Exception as e:
            print(f"[Recovery] 执行恢复策略失败: {e}")
            return {"recovered": False, "reason": str(e)}

    def clear_recovery_history(self):
        """清除恢复历史（新任务开始时调用）。"""
        self.recovery_history.clear()
