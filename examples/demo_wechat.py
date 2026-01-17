"""微信自动化演示 - 自动打开微信并发送消息."""

import asyncio
import sys

sys.path.insert(0, "src")

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.domain.value_objects.point import Point
from mobile_use.infrastructure.devices.android_controller import AndroidController


class WeChatAutomation:
    """微信自动化控制类."""

    WECHAT_PACKAGE = "com.tencent.mm"

    def __init__(self, controller: AndroidController):
        self.controller = controller
        self.screen_width = 1080
        self.screen_height = 1920

    async def init(self):
        """初始化屏幕信息."""
        screen = self.controller.device.screen_info
        self.screen_width = screen.width
        self.screen_height = screen.height

    async def open_wechat(self) -> bool:
        """打开微信应用."""
        print("  打开微信...")
        result = await self.controller.launch_app(self.WECHAT_PACKAGE)
        await asyncio.sleep(3)  # 等待微信启动
        return result.success

    async def find_and_click(self, text: str, timeout: int = 5) -> bool:
        """查找并点击包含指定文本的元素."""
        for _ in range(timeout):
            elements = await self.controller.get_ui_hierarchy()
            for elem in elements:
                elem_text = elem.get("text") or elem.get("content_desc") or ""
                if text in elem_text and elem.get("clickable"):
                    center = elem.get("center")
                    if center:
                        print(f"  点击: {text} @ ({center[0]}, {center[1]})")
                        await self.controller.tap(Point(center[0], center[1]))
                        await asyncio.sleep(1)
                        return True
            await asyncio.sleep(1)
        return False

    async def find_element_by_text(self, text: str) -> dict | None:
        """查找包含指定文本的元素."""
        elements = await self.controller.get_ui_hierarchy()
        for elem in elements:
            elem_text = elem.get("text") or elem.get("content_desc") or ""
            if text in elem_text:
                return elem
        return None

    async def click_contact(self, contact_name: str) -> bool:
        """点击联系人进入聊天."""
        print(f"  查找联系人: {contact_name}...")

        # 先点击搜索
        if await self.find_and_click("搜索"):
            await asyncio.sleep(1)

            # 输入联系人名称
            print(f"  输入: {contact_name}")
            await self.controller.input_text(contact_name)
            await asyncio.sleep(2)

            # 点击搜索结果
            return await self.find_and_click(contact_name)

        return False

    async def send_message(self, message: str) -> bool:
        """发送消息."""
        print(f"  发送消息: {message}")

        # 查找输入框并点击
        elements = await self.controller.get_ui_hierarchy()
        input_box = None
        for elem in elements:
            class_name = elem.get("class_name") or ""
            if "EditText" in class_name:
                input_box = elem
                break

        if input_box and input_box.get("center"):
            center = input_box["center"]
            await self.controller.tap(Point(center[0], center[1]))
            await asyncio.sleep(0.5)

        # 输入消息
        await self.controller.input_text(message)
        await asyncio.sleep(1)

        # 点击发送按钮
        return await self.find_and_click("发送")

    async def go_back(self):
        """返回上一页."""
        await self.controller.press_key("BACK")
        await asyncio.sleep(0.5)


async def main():
    print("=" * 60)
    print("Mobile-Use v2.0 - 微信自动化演示")
    print("=" * 60)

    # 配置
    CONTACT_NAME = "文件传输助手"  # 安全的测试对象
    MESSAGE = "Hello from Mobile-Use! 这是自动发送的测试消息。"

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

        wechat = WeChatAutomation(controller)
        await wechat.init()

        # 截图 - 初始状态
        await controller.take_screenshot("screenshots/wechat_1_start.png")

        # 打开微信
        print("\n[2] 打开微信...")
        if await wechat.open_wechat():
            print("    微信已打开")
            await controller.take_screenshot("screenshots/wechat_2_home.png")

            # 查找联系人
            print(f"\n[3] 查找联系人: {CONTACT_NAME}...")
            if await wechat.click_contact(CONTACT_NAME):
                print("    已进入聊天")
                await controller.take_screenshot("screenshots/wechat_3_chat.png")

                # 发送消息
                print(f"\n[4] 发送消息...")
                if await wechat.send_message(MESSAGE):
                    print("    消息已发送!")
                    await asyncio.sleep(1)
                    await controller.take_screenshot("screenshots/wechat_4_sent.png")
                else:
                    print("    发送失败")
            else:
                print("    未找到联系人")

            # 返回
            print("\n[5] 返回...")
            await wechat.go_back()
            await wechat.go_back()

        else:
            print("    打开微信失败")

        # 返回桌面
        await controller.press_key("HOME")

        print("\n" + "=" * 60)
        print("微信自动化演示完成!")
        print("截图保存在 screenshots/wechat_*.png")
        print("=" * 60)

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
