"""批量任务脚本 - 自动化测试流程."""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

sys.path.insert(0, "src")

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.domain.value_objects.point import Point
from mobile_use.infrastructure.devices.android_controller import AndroidController


@dataclass
class TestStep:
    """测试步骤."""
    name: str
    action: str
    params: dict = field(default_factory=dict)
    expected: str = ""
    timeout: float = 5.0


@dataclass
class TestCase:
    """测试用例."""
    name: str
    description: str
    steps: list[TestStep] = field(default_factory=list)
    setup: list[TestStep] = field(default_factory=list)
    teardown: list[TestStep] = field(default_factory=list)


@dataclass
class TestResult:
    """测试结果."""
    test_name: str
    success: bool
    duration_ms: int
    steps_passed: int
    steps_total: int
    error: str | None = None
    screenshots: list[str] = field(default_factory=list)


class BatchTestRunner:
    """批量测试执行器."""

    def __init__(self, controller: AndroidController):
        self.controller = controller
        self.results: list[TestResult] = []
        self.screenshot_dir = "screenshots/batch_test"

    async def run_step(self, step: TestStep) -> tuple[bool, str]:
        """执行单个测试步骤."""
        try:
            if step.action == "tap":
                x, y = step.params.get("x", 0), step.params.get("y", 0)
                result = await self.controller.tap(Point(x, y))
                return result.success, ""

            elif step.action == "tap_text":
                text = step.params.get("text", "")
                elements = await self.controller.get_ui_hierarchy()
                for elem in elements:
                    elem_text = elem.get("text") or elem.get("content_desc") or ""
                    if text in elem_text and elem.get("center"):
                        center = elem["center"]
                        result = await self.controller.tap(Point(center[0], center[1]))
                        return result.success, ""
                return False, f"未找到元素: {text}"

            elif step.action == "swipe":
                direction = step.params.get("direction", "down")
                screen = self.controller.device.screen_info
                cx, cy = screen.width // 2, screen.height // 2

                if direction == "up":
                    start, end = Point(cx, int(screen.height * 0.7)), Point(cx, int(screen.height * 0.3))
                elif direction == "down":
                    start, end = Point(cx, int(screen.height * 0.3)), Point(cx, int(screen.height * 0.7))
                elif direction == "left":
                    start, end = Point(int(screen.width * 0.8), cy), Point(int(screen.width * 0.2), cy)
                else:  # right
                    start, end = Point(int(screen.width * 0.2), cy), Point(int(screen.width * 0.8), cy)

                result = await self.controller.swipe(start, end)
                return result.success, ""

            elif step.action == "input":
                text = step.params.get("text", "")
                result = await self.controller.input_text(text)
                return result.success, ""

            elif step.action == "press":
                key = step.params.get("key", "BACK")
                result = await self.controller.press_key(key)
                return result.success, ""

            elif step.action == "wait":
                duration = step.params.get("duration", 1.0)
                await asyncio.sleep(duration)
                return True, ""

            elif step.action == "screenshot":
                name = step.params.get("name", "screenshot")
                path = f"{self.screenshot_dir}/{name}.png"
                result = await self.controller.take_screenshot(path)
                return result.success, path

            elif step.action == "launch_app":
                package = step.params.get("package", "")
                result = await self.controller.launch_app(package)
                return result.success, ""

            elif step.action == "assert_text":
                text = step.params.get("text", "")
                elements = await self.controller.get_ui_hierarchy()
                for elem in elements:
                    elem_text = elem.get("text") or elem.get("content_desc") or ""
                    if text in elem_text:
                        return True, ""
                return False, f"断言失败: 未找到文本 '{text}'"

            elif step.action == "assert_element":
                element_id = step.params.get("id", "")
                elements = await self.controller.get_ui_hierarchy()
                for elem in elements:
                    if element_id in (elem.get("id") or ""):
                        return True, ""
                return False, f"断言失败: 未找到元素 '{element_id}'"

            else:
                return False, f"未知操作: {step.action}"

        except Exception as e:
            return False, str(e)

    async def run_test(self, test: TestCase) -> TestResult:
        """执行单个测试用例."""
        print(f"\n{'='*50}")
        print(f"[测试] {test.name}")
        print(f"[描述] {test.description}")
        print("=" * 50)

        start_time = datetime.now()
        steps_passed = 0
        screenshots = []
        error = None

        # Setup
        if test.setup:
            print("\n[Setup]")
            for step in test.setup:
                success, msg = await self.run_step(step)
                if not success:
                    print(f"  Setup失败: {step.name} - {msg}")

        # 执行测试步骤
        print("\n[Steps]")
        for i, step in enumerate(test.steps):
            print(f"  {i+1}. {step.name}...", end=" ")

            success, msg = await self.run_step(step)

            if step.action == "screenshot" and msg:
                screenshots.append(msg)

            if success:
                print("PASS")
                steps_passed += 1
            else:
                print(f"FAIL - {msg}")
                error = f"步骤 {i+1} ({step.name}) 失败: {msg}"
                break

            await asyncio.sleep(0.5)

        # Teardown
        if test.teardown:
            print("\n[Teardown]")
            for step in test.teardown:
                await self.run_step(step)

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        result = TestResult(
            test_name=test.name,
            success=steps_passed == len(test.steps),
            duration_ms=duration,
            steps_passed=steps_passed,
            steps_total=len(test.steps),
            error=error,
            screenshots=screenshots
        )

        self.results.append(result)
        return result

    async def run_all(self, tests: list[TestCase]) -> list[TestResult]:
        """执行所有测试用例."""
        print("\n" + "=" * 60)
        print("Mobile-Use v2.0 - 批量自动化测试")
        print("=" * 60)
        print(f"\n共 {len(tests)} 个测试用例")

        for test in tests:
            await self.run_test(test)
            await asyncio.sleep(1)

        return self.results

    def print_summary(self):
        """打印测试摘要."""
        print("\n" + "=" * 60)
        print("测试摘要")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.success)
        failed = len(self.results) - passed
        total_duration = sum(r.duration_ms for r in self.results)

        print(f"\n总计: {len(self.results)} | 通过: {passed} | 失败: {failed}")
        print(f"总耗时: {total_duration}ms")

        print("\n详细结果:")
        for r in self.results:
            status = "PASS" if r.success else "FAIL"
            print(f"  [{status}] {r.test_name} ({r.steps_passed}/{r.steps_total}) - {r.duration_ms}ms")
            if r.error:
                print(f"         错误: {r.error}")

    def save_report(self, filename: str = "test_report.json"):
        """保存测试报告."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.success),
                "failed": sum(1 for r in self.results if not r.success),
                "duration_ms": sum(r.duration_ms for r in self.results)
            },
            "results": [
                {
                    "name": r.test_name,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                    "steps_passed": r.steps_passed,
                    "steps_total": r.steps_total,
                    "error": r.error,
                    "screenshots": r.screenshots
                }
                for r in self.results
            ]
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n测试报告已保存: {filename}")


# 预定义测试用例
def get_sample_tests() -> list[TestCase]:
    """获取示例测试用例."""
    return [
        TestCase(
            name="桌面导航测试",
            description="测试返回桌面和基本导航",
            setup=[
                TestStep("返回桌面", "press", {"key": "HOME"}),
                TestStep("等待", "wait", {"duration": 1}),
            ],
            steps=[
                TestStep("截图-桌面", "screenshot", {"name": "test1_home"}),
                TestStep("向左滑动", "swipe", {"direction": "left"}),
                TestStep("等待", "wait", {"duration": 0.5}),
                TestStep("截图-滑动后", "screenshot", {"name": "test1_swipe"}),
                TestStep("向右滑动", "swipe", {"direction": "right"}),
            ],
            teardown=[
                TestStep("返回桌面", "press", {"key": "HOME"}),
            ]
        ),

        TestCase(
            name="设置应用测试",
            description="测试打开设置应用",
            steps=[
                TestStep("返回桌面", "press", {"key": "HOME"}),
                TestStep("等待", "wait", {"duration": 1}),
                TestStep("打开设置", "launch_app", {"package": "com.android.settings"}),
                TestStep("等待加载", "wait", {"duration": 2}),
                TestStep("截图-设置", "screenshot", {"name": "test2_settings"}),
                TestStep("向下滑动", "swipe", {"direction": "down"}),
                TestStep("截图-滑动后", "screenshot", {"name": "test2_scroll"}),
            ],
            teardown=[
                TestStep("返回", "press", {"key": "BACK"}),
                TestStep("返回桌面", "press", {"key": "HOME"}),
            ]
        ),

        TestCase(
            name="滑动压力测试",
            description="连续滑动测试",
            steps=[
                TestStep("返回桌面", "press", {"key": "HOME"}),
                TestStep("向上滑动1", "swipe", {"direction": "up"}),
                TestStep("向上滑动2", "swipe", {"direction": "up"}),
                TestStep("向下滑动1", "swipe", {"direction": "down"}),
                TestStep("向下滑动2", "swipe", {"direction": "down"}),
                TestStep("截图", "screenshot", {"name": "test3_final"}),
            ]
        ),
    ]


async def main():
    os.makedirs("screenshots/batch_test", exist_ok=True)

    device = Device(
        device_id="emulator-5554",
        platform=DevicePlatform.ANDROID,
        name="MuMu Emulator"
    )
    controller = AndroidController(device)

    try:
        print("[初始化] 连接设备...")
        await controller.connect()
        print(f"[初始化] 已连接: {device.screen_info.width}x{device.screen_info.height}")

        # 创建测试运行器
        runner = BatchTestRunner(controller)

        # 获取测试用例
        tests = get_sample_tests()

        # 执行所有测试
        await runner.run_all(tests)

        # 打印摘要
        runner.print_summary()

        # 保存报告
        runner.save_report("screenshots/batch_test/test_report.json")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await controller.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
