"""Dynamic Task Planner - 动态任务规划模块

根据当前UI状态、总任务目标、已完成步骤，动态规划下一步操作。
"""

from dataclasses import dataclass, field
from typing import Any, Protocol
from enum import Enum


class LLMProvider(Protocol):
    """LLM提供者协议"""
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        ...


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UIContext:
    """当前UI上下文"""
    elements: list[dict[str, Any]] = field(default_factory=list)
    screenshot: bytes | None = None
    screen_info: dict[str, Any] = field(default_factory=dict)

    def _build_indexed_elements(self, clickable_only: bool = True) -> list[tuple[int, str, dict[str, Any]]]:
        """构建带编号的元素列表（不去重，使用位置区分同名元素）"""
        result = []
        idx = 1
        name_counter = {}  # 记录每个名称出现的次数
        
        for e in self.elements:
            text = e.get('text', '').strip()
            desc = e.get('content_desc', '').strip()
            clickable = e.get('clickable', False)
            class_name = e.get('class_name', '').lower() or e.get('class', '').lower()
            center = e.get('center', (0, 0))
            
            # 判断是否为输入框（即使没有名称也要包含）
            is_input = 'edittext' in class_name or 'input' in class_name
            
            # 生成名称：优先使用 text/desc，输入框用 hint 或类型标识
            name = text or desc
            
            # 特殊处理：缩短过长的名称（如热搜推荐、通知等）
            if name and len(name) > 30:
                # 保留前15字符 + ... + 后10字符
                name = name[:15] + "..." + name[-10:]
            
            if not name and is_input:
                hint = e.get('hint', '').strip()
                name = hint if hint else f"[输入框{idx}]"
            
            # 检查是否应该包含该元素
            should_include = False
            if clickable_only:
                should_include = name and (clickable or is_input)
            else:
                should_include = bool(name)
            
            if should_include:
                # 为同名元素添加位置后缀以区分
                display_name = name
                if name in name_counter:
                    name_counter[name] += 1
                    # 添加坐标后缀区分同名元素
                    display_name = f"{name}@({center[0]},{center[1]})"
                else:
                    name_counter[name] = 1
                
                result.append((idx, display_name, e))
                idx += 1
        
        return result

    def get_indexed_clickable_elements(self) -> list[tuple[int, str, dict[str, Any]]]:
        """获取带编号的可点击元素列表，返回 (编号, 名称, 元素)"""
        return self._build_indexed_elements(clickable_only=True)

    def get_indexed_all_elements(self) -> list[tuple[int, str, dict[str, Any]]]:
        """获取带编号的所有元素列表，返回 (编号, 名称, 元素)"""
        return self._build_indexed_elements(clickable_only=False)

    def get_element_by_index(self, index: int) -> dict[str, Any] | None:
        """根据编号获取元素（基于所有元素的统一编号）"""
        all_indexed = self._build_indexed_elements(clickable_only=False)
        if isinstance(index, int) and 1 <= index <= len(all_indexed):
            return all_indexed[index - 1][2]  # 返回元素 dict
        return None

    def get_clickable_elements(self) -> list[str]:
        """获取可点击元素名称列表"""
        return [name for _, name, _ in self.get_indexed_clickable_elements()]

    def get_all_elements(self) -> list[str]:
        """获取所有元素名称列表"""
        return [name for _, name, _ in self.get_indexed_all_elements()]

    def has_element(self, name: str) -> bool:
        """检查是否存在指定元素"""
        name_lower = name.lower()
        for e in self.elements:
            text = e.get('text', '').strip().lower()
            desc = e.get('content_desc', '').strip().lower()
            if name_lower in text or name_lower in desc:
                return True
        return False


@dataclass
class CompletedStep:
    """已完成的步骤"""
    action: str
    target: str | None
    description: str
    success: bool = True
    error: str | None = None  # 失败原因
    parameters: dict[str, Any] = field(default_factory=dict)  # 操作参数（如滑动方向）
    ui_before: list[str] = field(default_factory=list)  # 执行前的UI元素
    ui_after: list[str] = field(default_factory=list)   # 执行后的UI元素
    ui_changed: bool = True  # UI是否发生变化
    retry_count: int = 0  # 重试次数
    
    def to_string(self) -> str:
        """转换为字符串描述"""
        result = f"[{self.action}] {self.description}"
        if self.target:
            result += f" (目标: {self.target})"
        if self.success:
            result += " ✓"
            if not self.ui_changed:
                result += " (UI未变化)"
        else:
            result += " ✗"
            if self.error:
                result += f" 失败: {self.error}"
        if self.retry_count > 0:
            result += f" (重试{self.retry_count}次)"
        return result
    
    def to_detailed_string(self) -> str:
        """转换为详细字符串描述（包含UI变化）"""
        result = self.to_string()
        if self.ui_before and self.ui_after:
            # 计算UI变化
            before_set = set(self.ui_before)
            after_set = set(self.ui_after)
            new_elements = after_set - before_set
            removed_elements = before_set - after_set
            if new_elements:
                result += f" | 新增: {list(new_elements)[:3]}"
            if removed_elements:
                result += f" | 消失: {list(removed_elements)[:3]}"
        return result


@dataclass
class NextStep:
    """下一步操作"""
    action: str
    target: str | None = None
    target_index: int | None = None  # 元素编号
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "target_index": self.target_index,
            "parameters": self.parameters,
            "description": self.description
        }


@dataclass
class PlanningResult:
    """规划结果"""
    next_step: NextStep | None = None
    next_steps: list[NextStep] | None = None  # 批量操作时使用
    task_complete: bool = False
    reason: str = ""
    confidence: float = 0.8
    
    def has_batch_steps(self) -> bool:
        """是否有批量操作"""
        return self.next_steps is not None and len(self.next_steps) > 0
    
    def get_all_steps(self) -> list[NextStep]:
        """获取所有步骤（单步或批量）"""
        if self.has_batch_steps():
            return self.next_steps  # type: ignore
        elif self.next_step:
            return [self.next_step]
        return []


@dataclass
class TaskPlan:
    """总任务计划"""
    original_task: str  # 用户原始输入
    task_summary: str  # 任务摘要
    steps: list[str]  # 预期步骤列表
    potential_issues: list[str]  # 可能遇到的问题
    success_criteria: str  # 成功标准
    estimated_steps: int  # 预估步骤数
    confidence: float = 0.8


class DynamicTaskPlanner:
    """动态任务规划器
    
    核心逻辑：
    1. 分析总任务目标
    2. 查看当前UI状态
    3. 回顾已完成的步骤
    4. 规划下一步操作
    5. 重复直到任务完成
    """
    
    SYSTEM_PROMPT = """你是一个移动设备自动化任务规划助手。

**你的工作流程：**
1. 理解用户的总任务目标
2. 查看当前屏幕截图和UI元素（每个元素都有编号）
3. 回顾已完成的步骤（包括成功/失败状态和UI变化）
4. 根据历史信息决定下一步

**核心规则：**
1. 每次只规划一步操作
2. 只能操作当前屏幕上存在的元素
3. **点击元素时：**
   - 如果目标在元素列表中，使用 target_index 指定编号
   - **如果目标不在列表中但在截图中可见，必须使用 parameters: {"x": xxx, "y": yyy} 直接指定坐标**
   - **绝对不要随便猜一个编号！编号必须与元素列表中的名称完全对应**
4. 如果目标元素不在屏幕上，先滑动或导航找到它
5. **🔍 搜索任务的关键规则（重要！）：**
   - 看到搜索框时，**必须先输入搜索关键词**（tap搜索框 → input关键词 → press_key ENTER）
   - **不要点击热搜推荐！** 热搜推荐（如"XXX人气热搜"）不是用户想要的内容
   - **必须根据原始任务目标提取关键词输入**，例如：
     - 任务"搜索周杰伦的晴天" → 输入"晴天 周杰伦"或"晴天"
     - 任务"播放xxx的歌" → 输入歌曲名或歌手名
   - 只有在输入并搜索后，才能点击搜索结果

**重要：处理失败和边界情况**
- 如果上一步滑动后UI未变化，说明已到达边界，应该换方向或尝试其他操作
- 如果点击失败，检查目标元素是否真的存在于当前UI中
- 注意查看"⚠️"标记的警告信息，这些是需要特别注意的问题
- **失败时不要轻易返回桌面！先在当前页面思考其他解决办法：**
  - 尝试点击其他相关元素
  - 尝试不同方向的滑动
  - 尝试使用back返回上一级再重试
  - 只有在当前页面完全无法完成任务时，才考虑home回桌面

**重要：判断任务是否完成**
- 只有当屏幕已经显示了用户期望的最终状态时，才设置task_complete=true
- 如果还需要执行任何操作（包括home、back等），必须先规划该操作，task_complete=false

**可用操作：**
- click: 点击元素 (使用target_index指定编号，常规点击按钮、链接、图标等)
- tap: 轻触元素 (使用target_index指定编号，用于搜索框、输入框等需要获取焦点的场景)
  - **区别：click用于普通点击，tap用于需要激活/聚焦的输入控件**
  - **如果click多次失败，可尝试用tap**
- scroll: 滑动屏幕 (parameters: {"direction": "up/down/left/right"})
- input: 输入文本 (parameters: {"text": "内容"})
  - **当元素列表中有输入框时使用，可一次性输入全部内容（包括数字、密码）**
- press_key: 按键 (parameters: {"key": "按键名"})
  - 导航: ENTER, BACK, HOME, MENU, RECENT(最近任务)
  - 搜索: SEARCH
  - 音量: VOLUME_UP, VOLUME_DOWN
  - 电源: POWER
  - 方向: UP, DOWN, LEFT, RIGHT, CENTER
  - 编辑: TAB, DELETE/BACKSPACE
  - **搜索框没有搜索按钮时，输入文本后用 press_key ENTER 触发搜索**
- back: 返回上一页
- home: 回到桌面

**输入方式选择（重要）：**
- **有输入框**（元素列表中有EditText/输入框）→ 先tap输入框获取焦点，再用 `input` 直接输入全部内容
- **没有输入框，只有数字按钮**（如PIN码键盘、支付密码键盘）→ 用 `click` 批量点击数字按钮
- **判断依据**：看元素列表中是否有输入框，有就用input，没有就用click点击数字按钮

**批量操作（必须用于连续操作场景）：**
当需要连续执行多个简单操作时，**必须**使用 next_steps 返回多个操作，而不是一步一步执行：
- **必须使用批量操作的场景：**
  - 没有输入框时，点击数字键盘输入密码/PIN码（必须一次性返回多个click操作）
  - 连续选择多个选项
- **不适用批量操作的场景：**
  - 需要等待页面加载
  - 需要确认操作结果
  - 跨页面操作

**重要：先检查元素列表中是否有输入框！有输入框用input，没有输入框才用click点击数字按钮！**

**输出格式（JSON）：**

方式1 - 单步操作（常规情况）：
{
    "next_step": {
        "action": "click",
        "target_index": 5,
        "description": "点击第5个元素：哔哩哔哩"
    },
    "task_complete": false,
    "reason": "找到哔哩哔哩应用，点击打开"
}

方式2 - 直接指定坐标（当元素不在列表中，但在截图中可见时）：
{
    "next_step": {
        "action": "click",
        "parameters": {"x": 540, "y": 300},
        "description": "点击截图中的'取消'按钮"
    },
    "task_complete": false,
    "reason": "元素不在UI列表中，但在截图中可见，直接使用坐标点击"
}

方式3 - 批量操作（连续快速操作，如输入密码123456）：
{
    "next_steps": [
        {"action": "click", "target_index": 1, "description": "点击数字1"},
        {"action": "click", "target_index": 2, "description": "点击数字2"},
        {"action": "click", "target_index": 3, "description": "点击数字3"},
        {"action": "click", "target_index": 4, "description": "点击数字4"},
        {"action": "click", "target_index": 5, "description": "点击数字5"},
        {"action": "click", "target_index": 6, "description": "点击数字6"}
    ],
    "task_complete": false,
    "reason": "连续输入6位密码123456"
}

滑动操作：
{
    "next_step": {
        "action": "scroll",
        "parameters": {"direction": "up"},
        "description": "向上滑动查找目标"
    },
    "task_complete": false,
    "reason": "目标不在当前屏幕，向上滑动寻找"
}

任务完成：
{
    "next_step": null,
    "task_complete": true,
    "reason": "任务完成原因"
}
"""

    # 总任务规划的系统提示
    TASK_PLAN_PROMPT = """你是一个移动设备自动化任务规划专家。你需要将用户的简单任务描述转化为详细的执行计划。

**你的任务：**
1. 深入理解用户的真实意图和最终目标
2. 将任务拆解为具体、可执行的步骤序列
3. 每个步骤要足够详细，包含具体的操作对象和预期结果
4. 预测每个阶段可能遇到的问题和应对方案
5. 明确定义成功完成的判断标准

**步骤拆解要求：**
- 每个步骤必须是具体的操作，如"点击xxx按钮"、"在搜索框输入xxx"、"向下滑动查找xxx"
- 步骤之间要有逻辑顺序，前一步是后一步的前提
- 考虑应用的典型交互流程（如打开应用→导航到目标页面→执行操作→确认结果）
- 对于搜索类任务，要包含：打开应用、找到搜索入口、输入关键词、触发搜索、查看结果
- 对于发送消息类任务，要包含：打开应用、找到联系人、进入聊天、输入内容、发送

**请以JSON格式返回详细的任务计划：**
{
    "task_summary": "任务的完整描述，包含目标和关键操作",
    "steps": [
        "1. 在桌面找到并点击[应用名]图标，打开应用",
        "2. 等待应用加载完成，确认进入主界面",
        "3. 点击[具体按钮/入口]进入目标功能",
        "4. 在[输入框位置]输入[具体内容]",
        "5. 点击[搜索/发送按钮]或按回车确认",
        "6. 等待结果加载，确认操作成功",
        "7. [如有后续操作继续添加]"
    ],
    "potential_issues": [
        "应用可能需要登录 → 需要先完成登录流程",
        "目标元素可能不在当前屏幕 → 需要滑动查找",
        "网络加载慢 → 需要等待加载完成",
        "可能弹出广告或提示框 → 需要先关闭",
        "搜索框可能没有搜索按钮 → 使用回车键触发搜索"
    ],
    "success_criteria": "具体描述什么状态表示任务成功，如：看到xxx内容、消息显示已发送、页面显示xxx",
    "estimated_steps": 预估需要的操作步数（整数，要准确估计）,
    "confidence": 0.0-1.0之间的置信度
}

**示例 - 用户任务："打开抖音搜索美食视频"**
{
    "task_summary": "打开抖音应用，使用搜索功能查找美食相关视频",
    "steps": [
        "1. 在手机桌面找到抖音图标并点击打开",
        "2. 等待抖音启动，确认进入首页（显示推荐视频流）",
        "3. 点击顶部的搜索图标或搜索框进入搜索页面",
        "4. 在搜索输入框中输入关键词'美食'",
        "5. 点击搜索按钮或按回车键触发搜索",
        "6. 等待搜索结果加载完成",
        "7. 确认搜索结果页面显示美食相关视频"
    ],
    "potential_issues": [
        "抖音可能需要登录才能使用 → 需要先登录账号",
        "首次打开可能有开屏广告 → 等待或点击跳过",
        "搜索框可能在不同位置 → 可能需要滑动查找",
        "网络慢导致加载时间长 → 需要耐心等待"
    ],
    "success_criteria": "搜索结果页面显示与'美食'相关的视频列表",
    "estimated_steps": 8,
    "confidence": 0.9
}
"""

    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider
        self.current_task_plan: TaskPlan | None = None

    async def generate_task_plan(self, user_input: str, ui_context: UIContext | None = None) -> TaskPlan:
        """根据用户输入生成总任务计划
        
        Args:
            user_input: 用户的原始输入
            ui_context: 当前UI上下文（可选，用于更准确的规划）
            
        Returns:
            TaskPlan: 总任务计划
        """
        prompt = f"{self.TASK_PLAN_PROMPT}\n\n用户任务: {user_input}"
        
        # 如果有UI上下文，添加当前屏幕信息
        if ui_context and ui_context.elements:
            element_names = [e.get('text') or e.get('content_desc') for e in ui_context.elements[:20]]
            element_names = [n for n in element_names if n]
            prompt += f"\n\n当前屏幕可见元素（部分）: {element_names}"
        
        try:
            # 如果有截图，使用视觉模型
            if ui_context and ui_context.screenshot:
                print(f"[TaskPlan] 使用视觉模型分析当前屏幕...")
                response = await self.llm_provider.analyze_image(
                    ui_context.screenshot,
                    prompt
                )
            else:
                response = await self.llm_provider.generate(prompt)
            
            # 解析响应
            task_plan = self._parse_task_plan(user_input, response)
            self.current_task_plan = task_plan
            return task_plan
            
        except Exception as e:
            print(f"[TaskPlan] 生成任务计划失败: {e}")
            # 返回一个基本的计划
            return TaskPlan(
                original_task=user_input,
                task_summary=user_input,
                steps=[f"执行: {user_input}"],
                potential_issues=["任务规划失败，将直接尝试执行"],
                success_criteria="任务执行完成",
                estimated_steps=5,
                confidence=0.5
            )

    def _parse_task_plan(self, user_input: str, response: str) -> TaskPlan:
        """解析LLM返回的任务计划"""
        import json
        import re
        
        # 尝试提取JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return TaskPlan(
                    original_task=user_input,
                    task_summary=data.get("task_summary", user_input),
                    steps=data.get("steps", [user_input]),
                    potential_issues=data.get("potential_issues", []),
                    success_criteria=data.get("success_criteria", "任务完成"),
                    estimated_steps=data.get("estimated_steps", 5),
                    confidence=data.get("confidence", 0.8)
                )
            except json.JSONDecodeError:
                pass
        
        # 解析失败，返回基本计划
        return TaskPlan(
            original_task=user_input,
            task_summary=user_input,
            steps=[user_input],
            potential_issues=[],
            success_criteria="任务完成",
            estimated_steps=5,
            confidence=0.6
        )

    async def plan_next_step(
        self,
        task: str,
        ui_context: UIContext,
        completed_steps: list[CompletedStep]
    ) -> PlanningResult:
        """规划下一步操作
        
        Args:
            task: 总任务目标
            ui_context: 当前UI上下文
            completed_steps: 已完成的步骤列表
            
        Returns:
            PlanningResult: 规划结果
        """
        prompt = self._build_prompt(task, ui_context, completed_steps)
        
        try:
            # 如果有截图，使用视觉模型分析
            if ui_context.screenshot:
                img_size_kb = len(ui_context.screenshot) / 1024
                print(f"[DynamicPlanner] 使用视觉模型分析截图 (图片大小: {img_size_kb:.1f}KB, Prompt长度: {len(prompt)}字符)")
                import time
                start = time.time()
                response = await self.llm_provider.analyze_image(
                    ui_context.screenshot,
                    prompt
                )
                elapsed = time.time() - start
                print(f"[DynamicPlanner] LLM响应耗时: {elapsed:.2f}秒")
            else:
                response = await self.llm_provider.generate(prompt)
            return self._parse_response(response)
        except Exception as e:
            print(f"[DynamicPlanner] LLM调用失败: {e}")
            return self._fallback_plan(task, ui_context, completed_steps)
    
    def _build_prompt(
        self,
        task: str,
        ui_context: UIContext,
        completed_steps: list[CompletedStep]
    ) -> str:
        """构建LLM提示词"""
        prompt = f"{self.SYSTEM_PROMPT}\n\n"
        
        # 1. 总任务目标
        prompt += f"## 总任务目标\n{task}\n\n"
        
        # 1.1 检测搜索任务，提取并强调搜索关键词
        task_lower = task.lower()
        search_keywords = ["搜索", "查找", "找", "播放", "听", "看"]
        if any(kw in task_lower for kw in search_keywords):
            # 尝试提取关键词（歌名、歌手、应用名等）
            import re
            # 提取引号内的内容或明显的目标词
            quoted = re.findall(r'[《「『"](.+?)[》」』"]', task)
            if quoted:
                keywords = ' '.join(quoted)
                # 检查是否已经输入过搜索关键词
                has_searched = False
                for step in completed_steps:
                    if step.action == "input" and any(kw in (step.parameters.get("text", "") or "").lower() for kw in quoted):
                        has_searched = True
                        break
                
                if not has_searched:
                    prompt += f"⚠️ **关键提醒**：这是搜索任务！必须先输入关键词：**{keywords}**\n"
                    prompt += f"**重要**：还没有搜索过【{keywords}】！必须：\n"
                    prompt += "  1. 找到搜索框（通常在顶部或底部）\n"
                    prompt += f"  2. tap搜索框获取焦点\n"
                    prompt += f"  3. input '{keywords}'\n"
                    prompt += "  4. press_key ENTER 或点击搜索按钮\n"
                    prompt += "  5. 等待搜索结果出现后，才能点击结果\n"
                    prompt += "- **不要点击历史记录、热搜推荐或任何非搜索结果的内容！**\n\n"
                else:
                    prompt += f"✓ 已搜索关键词【{keywords}】，现在可以在搜索结果中选择\n"
                    prompt += "**选择歌曲时注意**：\n"
                    prompt += "  - 优先选择**原唱版本**（歌手名+歌曲名）\n"
                    prompt += "  - **避免选择**：伴奏、翻唱、Live版、DJ版（除非任务明确要求）\n"
                    prompt += "  - 如果误选了错误版本，使用 back 返回重新选择\n\n"
        
        # 1.2 如果有总任务计划，显示详细计划
        if self.current_task_plan:
            prompt += "## 总任务计划（AI预先规划）\n"
            prompt += f"任务摘要: {self.current_task_plan.task_summary}\n"
            prompt += "预期步骤:\n"
            for i, step in enumerate(self.current_task_plan.steps, 1):
                prompt += f"  {i}. {step}\n"
            if self.current_task_plan.potential_issues:
                prompt += "可能的问题:\n"
                for issue in self.current_task_plan.potential_issues:
                    prompt += f"  - {issue}\n"
            prompt += f"成功标准: {self.current_task_plan.success_criteria}\n"
            prompt += f"预估操作数: {self.current_task_plan.estimated_steps}\n\n"
        
        # 2. 已完成的步骤（包含详细信息）
        prompt += "## 已完成的步骤\n"
        if completed_steps:
            for i, step in enumerate(completed_steps, 1):
                prompt += f"  {i}. {step.to_detailed_string()}\n"
            
            # 分析最近的失败和问题
            recent_failures = [s for s in completed_steps[-5:] if not s.success]
            recent_no_change = [s for s in completed_steps[-3:] if s.success and not s.ui_changed]
            
            if recent_failures:
                prompt += "\n  ⚠️ 最近失败的操作:\n"
                for step in recent_failures:
                    prompt += f"    - {step.action}: {step.error}\n"
            
            if recent_no_change:
                prompt += "\n  ⚠️ 最近UI未变化的操作（可能已到边界或操作无效）:\n"
                for step in recent_no_change:
                    prompt += f"    - {step.action} {step.description}\n"
            
            # 检测连续UI未变化（页面卡住）
            consecutive_no_change = 0
            for step in reversed(completed_steps):
                if step.success and not step.ui_changed:
                    consecutive_no_change += 1
                else:
                    break
            
            if consecutive_no_change >= 2:
                prompt += f"\n  🚨 严重警告: 连续{consecutive_no_change}次操作后页面无变化！\n"
                prompt += "  必须立即改变策略：\n"
                last_action = completed_steps[-1].action if completed_steps else ""
                if last_action == "scroll":
                    # 获取最后滑动方向
                    last_dir = completed_steps[-1].parameters.get("direction", "")
                    prompt += f"  - 滑动方向'{last_dir}'已到边界，尝试反方向或其他操作\n"
                    prompt += "  - 可选：up↔down, left↔right 互换\n"
                elif last_action == "tap":
                    prompt += "  - 点击无效，目标可能不可交互，尝试其他元素\n"
                else:
                    prompt += "  - 当前操作无效，尝试完全不同的方法\n"
            
            # 检测重复相同操作
            if len(completed_steps) >= 3:
                last_actions = [
                    (s.action, s.target, s.parameters.get("direction", ""))
                    for s in completed_steps[-3:]
                ]
                if len({str(a) for a in last_actions}) == 1:
                    prompt += "\n  🚨 警告: 连续3次执行完全相同的操作，必须尝试不同的方法！\n"
            
            # 检测暂停/播放循环
            if len(completed_steps) >= 4:
                # 统计最近6步中暂停/播放相关的点击次数
                pause_play_actions = []
                for step in completed_steps[-6:]:
                    if step.action == "click" and step.description:
                        desc_lower = step.description.lower()
                        if "暂停" in desc_lower or "播放" in desc_lower or "pause" in desc_lower or "play" in desc_lower:
                            pause_play_actions.append(step)
                
                if len(pause_play_actions) >= 3:
                    prompt += "\n  🚨 严重警告: 检测到暂停/播放循环！\n"
                    prompt += "  - 反复点击暂停/播放无法解决问题\n"
                    prompt += "  - 可能原因：播放了错误的歌曲（如伴奏版）、广告、或其他内容\n"
                    prompt += "  - **必须改变策略**：\n"
                    prompt += "    1. 使用 back 返回上一页\n"
                    prompt += "    2. 重新搜索并选择正确的歌曲（注意区分原唱/伴奏/翻唱）\n"
                    prompt += "    3. 或者点击'下一曲'跳过当前内容\n"
                    prompt += "  - **禁止**继续点击暂停/播放按钮！\n\n"
        else:
            prompt += "  （这是第一步，还没有完成任何操作）\n"
        prompt += "\n"
        
        # 3. 当前UI状态（带编号，统一编号系统）
        prompt += "## 当前屏幕UI元素（使用编号指定操作目标）\n"
        prompt += "**注意：元素列表中的元素都是当前屏幕上可见的，不要根据坐标推断元素是否在屏幕外！**\n"
        # 使用统一的编号系统：所有元素共用一套编号
        all_indexed = ui_context.get_indexed_all_elements()

        if all_indexed:
            prompt += f"元素列表（共{len(all_indexed)}个，★表示可点击）:\n"
            # 显示所有元素，不跳过任何元素
            for idx, name, elem in all_indexed:
                clickable = elem.get('clickable', False)
                marker = "★" if clickable else " "
                prompt += f"  [{idx}]{marker} {name}\n"
        else:
            prompt += "  （未检测到UI元素）\n"
        
        # 4. 与上一步的UI对比（如果有）
        if completed_steps and completed_steps[-1].ui_before:
            last_step = completed_steps[-1]
            current_names = [name for _, name, _ in all_indexed]
            current_elements = set(current_names)
            prev_elements = set(last_step.ui_after) if last_step.ui_after else set(last_step.ui_before)

            new_elements = current_elements - prev_elements
            removed_elements = prev_elements - current_elements
            
            if new_elements or removed_elements:
                prompt += "\n## UI变化（与上一步对比）\n"
                if new_elements:
                    prompt += f"  新出现: {list(new_elements)[:5]}\n"
                if removed_elements:
                    prompt += f"  已消失: {list(removed_elements)[:5]}\n"
        
        # 5. 检测是否是密码/数字键盘场景，强制提醒使用批量操作
        element_names = [name.lower() for _, name, _ in all_indexed]
        element_names_str = " ".join(element_names)
        
        # 检测数字键盘特征：包含多个数字0-9
        digit_count = sum(1 for name in element_names if name in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'])
        has_password_hint = any(kw in element_names_str for kw in ['密码', 'password', 'pin', '验证码', '解锁'])
        
        if digit_count >= 6 or has_password_hint:
            prompt += "\n## ⚠️ 检测到数字键盘/密码输入界面！\n"
            prompt += "**必须使用 next_steps 批量操作一次性输入所有数字！**\n"
            prompt += "示例格式：\n"
            prompt += '{"next_steps": [{"action": "click", "target_index": 1, "description": "点击数字X"}, ...], "task_complete": false, "reason": "输入密码"}\n'
            prompt += "**禁止一个数字一个数字地单独返回！**\n\n"
        
        prompt += "\n## 请规划下一步操作\n"
        prompt += "根据以上信息，特别注意失败的操作和UI变化，规划最合适的下一步。\n"
        
        return prompt
    
    def _parse_response(self, response: str) -> PlanningResult:
        """解析LLM响应"""
        import json
        
        # 提取JSON
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[DynamicPlanner] JSON解析失败: {e}")
            return PlanningResult(reason=f"JSON解析失败: {response[:100]}")
        
        task_complete = data.get("task_complete", False)
        reason = data.get("reason", "")
        
        # 只有明确标记 task_complete=true 才算完成
        if task_complete:
            return PlanningResult(
                task_complete=True,
                reason=reason
            )
        
        # 检查是否有批量操作 next_steps
        if data.get("next_steps"):
            steps_data = data.get("next_steps", [])
            next_steps = []
            for step_data in steps_data:
                step = NextStep(
                    action=step_data.get("action", "tap"),
                    target=step_data.get("target"),
                    target_index=step_data.get("target_index"),
                    parameters=step_data.get("parameters", {}),
                    description=step_data.get("description", "")
                )
                next_steps.append(step)
            
            print(f"[DynamicPlanner] 批量操作: {len(next_steps)} 个步骤")
            return PlanningResult(
                next_steps=next_steps,
                task_complete=False,
                reason=reason,
                confidence=data.get("confidence", 0.8)
            )
        
        # 单步操作
        if data.get("next_step") is None:
            print(f"[DynamicPlanner] 警告: next_step为空但task_complete=false")
            return PlanningResult(reason="LLM未返回有效的下一步操作")
        
        step_data = data.get("next_step", {})
        next_step = NextStep(
            action=step_data.get("action", "tap"),
            target=step_data.get("target"),
            target_index=step_data.get("target_index"),  # 解析元素编号
            parameters=step_data.get("parameters", {}),
            description=step_data.get("description", "")
        )
        
        return PlanningResult(
            next_step=next_step,
            task_complete=False,
            reason=reason,
            confidence=data.get("confidence", 0.8)
        )
    
    def _fallback_plan(
        self,
        task: str,
        ui_context: UIContext,
        completed_steps: list[CompletedStep]
    ) -> PlanningResult:
        """后备规划（当LLM失败时，如速率限制等错误）
        
        注意：LLM调用失败不代表任务失败，应该等待重试而不是执行任何操作
        """
        # LLM调用失败时，不执行任何操作，返回空让系统等待重试
        return PlanningResult(
            next_step=None,
            task_complete=False,
            reason="LLM调用失败（可能是速率限制），等待重试",
            confidence=0.0
        )


class TaskExecutionManager:
    """任务执行管理器
    
    管理整个任务的执行流程：
    1. 初始化任务
    2. 循环执行：规划 -> 执行 -> 记录
    3. 直到任务完成或达到最大步数
    """
    
    def __init__(
        self,
        planner: DynamicTaskPlanner,
        max_steps: int = 10
    ):
        self.planner = planner
        self.max_steps = max_steps
        self.completed_steps: list[CompletedStep] = []
        self.current_task: str = ""
        self.status = TaskStatus.PENDING
    
    def start_task(self, task: str) -> None:
        """开始新任务"""
        self.current_task = task
        self.completed_steps = []
        self.status = TaskStatus.IN_PROGRESS
        print(f"[TaskManager] 开始任务: {task}")
    
    async def get_next_step(self, ui_context: UIContext) -> PlanningResult:
        """获取下一步操作"""
        if self.status != TaskStatus.IN_PROGRESS:
            return PlanningResult(task_complete=True, reason="任务未在进行中")
        
        if len(self.completed_steps) >= self.max_steps:
            self.status = TaskStatus.FAILED
            return PlanningResult(task_complete=True, reason=f"达到最大步数限制({self.max_steps})")
        
        result = await self.planner.plan_next_step(
            self.current_task,
            ui_context,
            self.completed_steps
        )
        
        if result.task_complete:
            self.status = TaskStatus.COMPLETED
        
        return result
    
    def record_step(self, step: CompletedStep) -> None:
        """记录已完成的步骤"""
        self.completed_steps.append(step)
        print(f"[TaskManager] 完成步骤 {len(self.completed_steps)}: {step.to_string()}")
    
    def get_progress(self) -> dict[str, Any]:
        """获取任务进度"""
        return {
            "task": self.current_task,
            "status": self.status.value,
            "completed_steps": len(self.completed_steps),
            "max_steps": self.max_steps,
            "steps": [
                {
                    "action": s.action,
                    "target": s.target,
                    "description": s.description,
                    "success": s.success
                }
                for s in self.completed_steps
            ]
        }
