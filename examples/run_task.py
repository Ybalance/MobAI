"""执行AI驱动的自动化任务示例."""

import asyncio
import os
import sys

sys.path.insert(0, "src")

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.domain.value_objects.point import Point
from mobile_use.infrastructure.devices.android_controller import AndroidController
from mobile_use.infrastructure.llm.base import LLMConfig, LLMProviderType
from mobile_use.infrastructure.llm.openai_provider import OpenAIProvider
from mobile_use.domain.services.agents.orchestrator import AgentOrchestrator
from mobile_use.domain.services.agents.task_planner import TaskPlannerAgent
from mobile_use.domain.services.agents.context_analyzer import ContextAnalyzerAgent
from mobile_use.domain.services.agents.action_executor import ActionExecutorAgent
from mobile_use.domain.services.agents.result_validator import ResultValidatorAgent


async def run_simple_task():
    """运行简单的自动化任务（不使用AI）."""
    print("\n" + "=" * 60)
    print("Mobile-Use v2.0 - 简单自动化任务")
    print("=" * 60)

    # 连接设备
    device = Device(
        device_id="emulator-5554",
        platform=DevicePlatform.ANDROID,
        name="MuMu Emulator"
    )
    controller = AndroidController(device)

    try:
        print("\n[1] 连接模拟器...")
        await controller.connect()
        print(f"    已连接: {device.screen_info.width}x{device.screen_info.height}")

        # 截图
        print("\n[2] 截取当前屏幕...")
        await controller.take_screenshot("screenshots/before_task.png")

        # 获取屏幕中心点
        screen = device.screen_info
        center = Point(screen.width // 2, screen.height // 2)

        # 示例操作：从屏幕中间向上滑动（模拟下拉刷新）
        print("\n[3] 执行滑动操作...")
        start = Point(center.x, int(screen.height * 0.3))
        end = Point(center.x, int(screen.height * 0.7))
        result = await controller.swipe(start, end, duration_ms=500)
        print(f"    滑动: {result.success}")

        await asyncio.sleep(1)

        # 再次截图
        print("\n[4] 截取操作后屏幕...")
        await controller.take_screenshot("screenshots/after_task.png")

        # 按返回键
        print("\n[5] 按返回键...")
        result = await controller.press_key("BACK")
        print(f"    返回: {result.success}")

        print("\n任务完成!")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await controller.disconnect()


async def run_ai_task(instruction: str):
    """运行AI驱动的自动化任务."""
    print("\n" + "=" * 60)
    print("Mobile-Use v2.0 - AI自动化任务")
    print("=" * 60)
    print(f"\n指令: {instruction}")

    # 连接设备
    device = Device(
        device_id="emulator-5554",
        platform=DevicePlatform.ANDROID,
        name="MuMu Emulator"
    )
    controller = AndroidController(device)

    try:
        print("\n[1] 连接模拟器...")
        await controller.connect()
        print(f"    已连接: {device.screen_info.width}x{device.screen_info.height}")

        # 获取初始截图和UI层级
        print("\n[2] 分析当前屏幕...")
        screenshot_result = await controller.take_screenshot()
        screenshot_data = screenshot_result.data.get("screenshot") if screenshot_result.success else None

        ui_elements = await controller.get_ui_hierarchy()
        print(f"    找到 {len(ui_elements)} 个UI元素")

        # 配置LLM（使用DeepSeek）
        print("\n[3] 初始化AI代理...")
        llm_config = LLMConfig(
            provider=LLMProviderType.OPENAI,
            model="deepseek-v3",
            api_key=os.getenv("LLM_API_KEY", "sk-I8yPynC3wWW8PMYxSeJanLTRsj5qsF1lLh4vbd929nkWLgb8"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.chat.csu.edu.cn/v1"),
            temperature=0.7,
            max_tokens=2048
        )
        llm_provider = OpenAIProvider(llm_config)
        await llm_provider.initialize()

        # 创建代理
        task_planner = TaskPlannerAgent(llm_provider=llm_provider)
        context_analyzer = ContextAnalyzerAgent(vision_provider=None)
        action_executor = ActionExecutorAgent(device_controller=controller)
        result_validator = ResultValidatorAgent()

        # 创建协调器
        orchestrator = AgentOrchestrator(
            task_planner=task_planner,
            context_analyzer=context_analyzer,
            action_executor=action_executor,
            result_validator=result_validator,
            max_iterations=10
        )

        # 执行任务
        print("\n[4] 执行AI任务...")
        result = await orchestrator.execute_task(
            instruction=instruction,
            device_id=device.device_id,
            initial_screenshot=screenshot_data,
            initial_ui_elements=ui_elements,
            screen_info={
                "width": device.screen_info.width,
                "height": device.screen_info.height,
                "app_name": "Unknown"
            }
        )

        # 输出结果
        print("\n" + "-" * 40)
        print("执行结果:")
        print(f"  成功: {result.success}")
        print(f"  执行步骤: {result.steps_executed}/{result.total_steps}")
        print(f"  耗时: {result.duration_ms}ms")

        if result.actions:
            print(f"\n  执行的操作:")
            for i, action in enumerate(result.actions):
                print(f"    {i+1}. {action.get('action', 'unknown')}: {action.get('target', 'N/A')}")

        if result.error:
            print(f"\n  错误: {result.error}")

        # 最终截图
        print("\n[5] 保存最终截图...")
        await controller.take_screenshot("screenshots/ai_task_result.png")

        await llm_provider.close()

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await controller.disconnect()


async def interactive_control():
    """交互式控制模式."""
    print("\n" + "=" * 60)
    print("Mobile-Use v2.0 - 交互式控制")
    print("=" * 60)

    device = Device(
        device_id="emulator-5554",
        platform=DevicePlatform.ANDROID,
        name="MuMu Emulator"
    )
    controller = AndroidController(device)

    try:
        await controller.connect()
        screen = device.screen_info
        print(f"\n已连接: {screen.width}x{screen.height}")

        print("\n可用命令:")
        print("  tap <x> <y>     - 点击坐标")
        print("  swipe <方向>    - 滑动 (up/down/left/right)")
        print("  input <文本>    - 输入文本")
        print("  back            - 返回")
        print("  home            - 主页")
        print("  screenshot      - 截图")
        print("  elements        - 显示UI元素")
        print("  quit            - 退出")

        while True:
            try:
                cmd = input("\n> ").strip().lower()

                if cmd == "quit" or cmd == "exit":
                    break

                elif cmd.startswith("tap "):
                    parts = cmd.split()
                    if len(parts) == 3:
                        x, y = int(parts[1]), int(parts[2])
                        result = await controller.tap(Point(x, y))
                        print(f"点击 ({x}, {y}): {result.success}")

                elif cmd.startswith("swipe "):
                    direction = cmd.split()[1]
                    cx, cy = screen.width // 2, screen.height // 2
                    if direction == "up":
                        start, end = Point(cx, int(screen.height * 0.7)), Point(cx, int(screen.height * 0.3))
                    elif direction == "down":
                        start, end = Point(cx, int(screen.height * 0.3)), Point(cx, int(screen.height * 0.7))
                    elif direction == "left":
                        start, end = Point(int(screen.width * 0.8), cy), Point(int(screen.width * 0.2), cy)
                    elif direction == "right":
                        start, end = Point(int(screen.width * 0.2), cy), Point(int(screen.width * 0.8), cy)
                    else:
                        print("方向: up/down/left/right")
                        continue
                    result = await controller.swipe(start, end)
                    print(f"滑动 {direction}: {result.success}")

                elif cmd.startswith("input "):
                    text = cmd[6:]
                    result = await controller.input_text(text)
                    print(f"输入: {result.success}")

                elif cmd == "back":
                    result = await controller.press_key("BACK")
                    print(f"返回: {result.success}")

                elif cmd == "home":
                    result = await controller.press_key("HOME")
                    print(f"主页: {result.success}")

                elif cmd == "screenshot":
                    result = await controller.take_screenshot("screenshots/interactive.png")
                    print(f"截图: {result.success}")

                elif cmd == "elements":
                    elements = await controller.get_ui_hierarchy()
                    print(f"\n找到 {len(elements)} 个元素:")
                    for i, elem in enumerate(elements[:15]):
                        text = elem.get("text") or elem.get("content_desc") or ""
                        if text:
                            center = elem.get("center", (0, 0))
                            print(f"  {i+1}. [{center[0]},{center[1]}] {text[:40]}")

                else:
                    print("未知命令，输入 'quit' 退出")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"错误: {e}")

    finally:
        await controller.disconnect()
        print("\n已断开连接")


def main():
    """主函数."""
    os.makedirs("screenshots", exist_ok=True)

    print("\n" + "=" * 60)
    print("Mobile-Use v2.0 - 自动化任务演示")
    print("=" * 60)
    print("\n选择模式:")
    print("  1. 简单任务 (滑动+返回)")
    print("  2. AI任务 (自然语言指令)")
    print("  3. 交互式控制")
    print("  4. 退出")

    choice = input("\n请选择 (1-4): ").strip()

    if choice == "1":
        asyncio.run(run_simple_task())
    elif choice == "2":
        instruction = input("\n请输入任务指令: ").strip()
        if instruction:
            asyncio.run(run_ai_task(instruction))
    elif choice == "3":
        asyncio.run(interactive_control())
    else:
        print("退出")


if __name__ == "__main__":
    main()
