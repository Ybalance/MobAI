"""简单自动化任务演示 - 直接运行."""

import asyncio
import sys

sys.path.insert(0, "src")

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.domain.value_objects.point import Point
from mobile_use.infrastructure.devices.android_controller import AndroidController


async def main():
    print("=" * 50)
    print("Mobile-Use v2.0 - 简单自动化演示")
    print("=" * 50)

    device = Device(
        device_id="emulator-5554",
        platform=DevicePlatform.ANDROID,
        name="MuMu Emulator"
    )
    controller = AndroidController(device)

    try:
        # 连接
        print("\n[1] 连接模拟器...")
        await controller.connect()
        screen = device.screen_info
        print(f"    屏幕: {screen.width}x{screen.height}")

        # 截图
        print("\n[2] 截取屏幕...")
        await controller.take_screenshot("screenshots/demo_1.png")
        print("    保存: screenshots/demo_1.png")

        # 按Home键回到桌面
        print("\n[3] 返回桌面...")
        await controller.press_key("HOME")
        await asyncio.sleep(1)

        # 截图
        print("\n[4] 截取桌面...")
        await controller.take_screenshot("screenshots/demo_2_home.png")
        print("    保存: screenshots/demo_2_home.png")

        # 获取UI元素
        print("\n[5] 获取桌面应用...")
        elements = await controller.get_ui_hierarchy()
        apps = [e for e in elements if e.get("clickable") and (e.get("text") or e.get("content_desc"))]
        print(f"    找到 {len(apps)} 个可点击元素")

        # 显示前10个应用
        print("\n    桌面应用:")
        for i, app in enumerate(apps[:10]):
            name = app.get("text") or app.get("content_desc") or "未知"
            center = app.get("center", (0, 0))
            print(f"    {i+1}. {name} @ ({center[0]}, {center[1]})")

        # 点击第一个应用（如果有）
        if apps:
            first_app = apps[0]
            name = first_app.get("text") or first_app.get("content_desc")
            center = first_app.get("center")
            if center:
                print(f"\n[6] 点击应用: {name}...")
                await controller.tap(Point(center[0], center[1]))
                await asyncio.sleep(2)

                # 截图
                print("\n[7] 截取应用界面...")
                await controller.take_screenshot("screenshots/demo_3_app.png")
                print("    保存: screenshots/demo_3_app.png")

        # 滑动演示
        print("\n[8] 向上滑动...")
        start = Point(screen.width // 2, int(screen.height * 0.7))
        end = Point(screen.width // 2, int(screen.height * 0.3))
        await controller.swipe(start, end, duration_ms=500)
        await asyncio.sleep(1)

        # 截图
        await controller.take_screenshot("screenshots/demo_4_swipe.png")
        print("    保存: screenshots/demo_4_swipe.png")

        # 返回
        print("\n[9] 按返回键...")
        await controller.press_key("BACK")
        await asyncio.sleep(0.5)
        await controller.press_key("HOME")

        print("\n" + "=" * 50)
        print("演示完成! 截图保存在 screenshots/ 目录")
        print("=" * 50)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await controller.disconnect()


if __name__ == "__main__":
    import os
    os.makedirs("screenshots", exist_ok=True)
    asyncio.run(main())
