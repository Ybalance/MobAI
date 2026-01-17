"""AI任务执行 - 用自然语言控制手机."""

import asyncio
import os
import sys

sys.path.insert(0, "src")

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.infrastructure.devices.android_controller import AndroidController
from mobile_use.infrastructure.llm.base import LLMConfig, LLMProviderType
from mobile_use.infrastructure.llm.openai_provider import OpenAIProvider
from mobile_use.domain.services.agents.orchestrator import AgentOrchestrator
from mobile_use.domain.services.agents.task_planner import TaskPlannerAgent
from mobile_use.domain.services.agents.context_analyzer import ContextAnalyzerAgent
from mobile_use.domain.services.agents.action_executor import ActionExecutorAgent
from mobile_use.domain.services.agents.result_validator import ResultValidatorAgent


class AITaskExecutor:
    """AI驱动的任务执行器."""

    def __init__(self):
        self.device = None
        self.controller = None
        self.llm_provider = None
        self.orchestrator = None

    async def initialize(self, device_id: str = "emulator-5554"):
        """初始化设备和AI组件."""
        print("[初始化] 连接设备...")

        # 连接设备
        self.device = Device(
            device_id=device_id,
            platform=DevicePlatform.ANDROID,
            name="MuMu Emulator"
        )
        self.controller = AndroidController(self.device)
        await self.controller.connect()

        screen = self.device.screen_info
        print(f"[初始化] 设备已连接: {screen.width}x{screen.height}")

        # 初始化LLM
        print("[初始化] 加载AI模型...")
        llm_config = LLMConfig(
            provider=LLMProviderType.OPENAI,
            model="deepseek-v3",
            api_key=os.getenv("LLM_API_KEY", "sk-I8yPynC3wWW8PMYxSeJanLTRsj5qsF1lLh4vbd929nkWLgb8"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.chat.csu.edu.cn/v1"),
            temperature=0.7,
            max_tokens=2048
        )
        self.llm_provider = OpenAIProvider(llm_config)
        await self.llm_provider.initialize()

        # 创建代理
        task_planner = TaskPlannerAgent(llm_provider=self.llm_provider)
        context_analyzer = ContextAnalyzerAgent()
        action_executor = ActionExecutorAgent(device_controller=self.controller)
        result_validator = ResultValidatorAgent()

        self.orchestrator = AgentOrchestrator(
            task_planner=task_planner,
            context_analyzer=context_analyzer,
            action_executor=action_executor,
            result_validator=result_validator,
            max_iterations=15
        )

        print("[初始化] AI系统就绪!")

    async def execute(self, instruction: str) -> dict:
        """执行自然语言指令."""
        print(f"\n{'='*50}")
        print(f"[AI任务] {instruction}")
        print("=" * 50)

        # 获取当前屏幕状态
        print("\n[分析] 获取屏幕状态...")
        screenshot_result = await self.controller.take_screenshot()
        screenshot_data = screenshot_result.data.get("screenshot") if screenshot_result.success else None

        ui_elements = await self.controller.get_ui_hierarchy()
        print(f"[分析] 找到 {len(ui_elements)} 个UI元素")

        # 显示可交互元素
        clickable = [e for e in ui_elements if e.get("clickable") and (e.get("text") or e.get("content_desc"))]
        if clickable:
            print("[分析] 可交互元素:")
            for elem in clickable[:8]:
                name = elem.get("text") or elem.get("content_desc")
                print(f"       - {name}")

        # 执行AI任务
        print("\n[执行] AI正在规划任务...")
        result = await self.orchestrator.execute_task(
            instruction=instruction,
            device_id=self.device.device_id,
            initial_screenshot=screenshot_data,
            initial_ui_elements=ui_elements,
            screen_info={
                "width": self.device.screen_info.width,
                "height": self.device.screen_info.height
            }
        )

        # 输出结果
        print(f"\n[结果] 执行{'成功' if result.success else '失败'}")
        print(f"[结果] 步骤: {result.steps_executed}/{result.total_steps}")
        print(f"[结果] 耗时: {result.duration_ms}ms")

        if result.actions:
            print("[结果] 执行的操作:")
            for action in result.actions:
                print(f"       - {action.get('action')}: {action.get('target', 'N/A')}")

        if result.error:
            print(f"[错误] {result.error}")

        # 保存截图
        await self.controller.take_screenshot(f"screenshots/ai_result_{len(os.listdir('screenshots'))}.png")

        return {
            "success": result.success,
            "steps": result.steps_executed,
            "actions": result.actions,
            "error": result.error
        }

    async def close(self):
        """关闭连接."""
        if self.llm_provider:
            await self.llm_provider.close()
        if self.controller:
            await self.controller.disconnect()
        print("\n[关闭] 已断开连接")


async def main():
    print("=" * 60)
    print("Mobile-Use v2.0 - AI自然语言任务执行")
    print("=" * 60)

    # 示例任务列表
    DEMO_TASKS = [
        "返回桌面",
        "打开设置",
        "向下滑动",
        "返回上一页",
    ]

    executor = AITaskExecutor()

    try:
        await executor.initialize()

        print("\n" + "-" * 40)
        print("示例任务:")
        for i, task in enumerate(DEMO_TASKS):
            print(f"  {i+1}. {task}")
        print("-" * 40)

        # 执行示例任务
        for task in DEMO_TASKS[:2]:  # 只执行前2个作为演示
            await executor.execute(task)
            await asyncio.sleep(2)

        print("\n" + "=" * 60)
        print("AI任务演示完成!")
        print("=" * 60)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await executor.close()


async def interactive_mode():
    """交互模式 - 输入自然语言指令."""
    print("=" * 60)
    print("Mobile-Use v2.0 - AI交互模式")
    print("=" * 60)
    print("\n输入自然语言指令，AI将自动执行")
    print("输入 'quit' 退出\n")

    executor = AITaskExecutor()

    try:
        await executor.initialize()

        while True:
            try:
                instruction = input("\n[指令] > ").strip()

                if instruction.lower() in ["quit", "exit", "q"]:
                    break

                if not instruction:
                    continue

                await executor.execute(instruction)

            except KeyboardInterrupt:
                break

    finally:
        await executor.close()


if __name__ == "__main__":
    import os
    os.makedirs("screenshots", exist_ok=True)

    # 选择模式
    print("\n选择模式:")
    print("  1. 演示模式 (自动执行示例任务)")
    print("  2. 交互模式 (手动输入指令)")

    mode = input("\n请选择 (1/2): ").strip()

    if mode == "2":
        asyncio.run(interactive_mode())
    else:
        asyncio.run(main())
