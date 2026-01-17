"""测试MuMu模拟器连接的示例脚本."""

import asyncio
import sys
sys.path.insert(0, "src")

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.infrastructure.devices.android_controller import AndroidController


async def main():
    print("=" * 50)
    print("Mobile-Use v2.0 - MuMu模拟器连接测试")
    print("=" * 50)

    # 创建设备对象
    device = Device(
        device_id="emulator-5554",  # MuMu模拟器设备ID
        platform=DevicePlatform.ANDROID,
        name="MuMu Emulator"
    )

    print(f"\n[1] 创建设备: {device.name}")
    print(f"    设备ID: {device.device_id}")
    print(f"    平台: {device.platform.value}")

    # 创建控制器
    controller = AndroidController(device)

    try:
        # 连接设备
        print("\n[2] 正在连接模拟器...")
        connected = await controller.connect()

        if connected:
            print("    连接成功!")
            print(f"    型号: {device.model}")
            print(f"    屏幕: {device.screen_info.width}x{device.screen_info.height}")

            # 截图测试
            print("\n[3] 正在截图...")
            result = await controller.take_screenshot("screenshots/test_mumu.png")
            if result.success:
                print(f"    截图成功! 保存到: screenshots/test_mumu.png")
            else:
                print(f"    截图失败: {result.error}")

            # 获取UI层级
            print("\n[4] 获取UI元素...")
            elements = await controller.get_ui_hierarchy()
            print(f"    找到 {len(elements)} 个UI元素")

            if elements:
                print("\n    前5个元素:")
                for i, elem in enumerate(elements[:5]):
                    text = elem.get("text") or elem.get("content_desc") or "(无文本)"
                    print(f"    {i+1}. {text[:30]}")

            # 断开连接
            print("\n[5] 断开连接...")
            await controller.disconnect()
            print("    已断开")

        else:
            print("    连接失败!")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    # 创建screenshots目录
    import os
    os.makedirs("screenshots", exist_ok=True)

    asyncio.run(main())
