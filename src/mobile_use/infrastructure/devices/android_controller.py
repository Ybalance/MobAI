"""Android device controller implementation using ADB and UIAutomator2."""

import asyncio
import io
from typing import Any

from mobile_use.domain.entities.device import Device, DevicePlatform, DeviceStatus
from mobile_use.domain.value_objects.point import Point
from mobile_use.domain.value_objects.screen_info import ScreenInfo
from mobile_use.infrastructure.devices.base_controller import (
    ActionResult,
    ActionType,
    DeviceController,
    ElementSelector,
    UIElement,
)


class AndroidController(DeviceController):
    """Android device controller using UIAutomator2.

    This controller provides full Android device automation capabilities
    through the UIAutomator2 framework and ADB.
    """

    def __init__(self, device: Device, adb_host: str = "localhost", adb_port: int = 5037):
        super().__init__(device)
        self.adb_host = adb_host
        self.adb_port = adb_port
        self._u2_device: Any = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Android device using UIAutomator2."""
        try:
            import uiautomator2 as u2

            device_id = self.device.device_id or None

            # Connect to device
            if device_id:
                self._u2_device = u2.connect(device_id)
            else:
                self._u2_device = u2.connect()

            # Verify connection
            info = self._u2_device.info
            if info:
                self._connected = True
                self.device.connect()

                # Update device info
                self.device.model = info.get("productName", "")
                self.device.platform_version = info.get("sdkInt", "")

                # Get screen info
                window_size = self._u2_device.window_size()
                self.device.screen_info = ScreenInfo(
                    width=window_size[0],
                    height=window_size[1],
                    density=info.get("displaySizeDpX", 1.0),
                    orientation="portrait" if window_size[1] > window_size[0] else "landscape"
                )

                return True

        except ImportError:
            raise ImportError(
                "uiautomator2 package not installed. "
                "Install with: pip install uiautomator2"
            )
        except Exception as e:
            self.device.set_error()
            raise ConnectionError(f"Failed to connect to Android device: {e}")

        return False

    async def disconnect(self) -> None:
        """Disconnect from Android device."""
        self._connected = False
        self._u2_device = None
        self.device.disconnect()

    async def is_connected(self) -> bool:
        """Check if device is connected."""
        if not self._connected or not self._u2_device:
            return False

        try:
            # Quick health check
            self._u2_device.info
            return True
        except Exception:
            self._connected = False
            return False

    async def get_screen_info(self) -> ScreenInfo:
        """Get current screen information."""
        if not await self.is_connected():
            raise ConnectionError("Device not connected")

        window_size = self._u2_device.window_size()
        info = self._u2_device.info

        return ScreenInfo(
            width=window_size[0],
            height=window_size[1],
            density=info.get("displaySizeDpX", 1.0),
            orientation="portrait" if window_size[1] > window_size[0] else "landscape"
        )

    async def take_screenshot(self, save_path: str | None = None) -> ActionResult:
        """Take a screenshot of the device screen."""
        if not await self.is_connected():
            return ActionResult(
                success=False,
                action_type=ActionType.SCREENSHOT,
                error="Device not connected"
            )

        try:
            # Get screenshot as PIL Image
            image = self._u2_device.screenshot()

            # Convert to bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format="PNG")
            screenshot_data = img_bytes.getvalue()

            # Save to file if path provided
            if save_path:
                with open(save_path, "wb") as f:
                    f.write(screenshot_data)

            return ActionResult(
                success=True,
                action_type=ActionType.SCREENSHOT,
                data={"screenshot": screenshot_data, "path": save_path},
                screenshot_path=save_path
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.SCREENSHOT,
                error=str(e)
            )

    async def tap(self, point: Point) -> ActionResult:
        """Tap at the specified point."""
        if not await self.is_connected():
            return ActionResult(
                success=False,
                action_type=ActionType.TAP,
                error="Device not connected"
            )

        try:
            self._u2_device.click(point.x, point.y)
            await asyncio.sleep(0.3)  # Brief delay for action to complete

            return ActionResult(
                success=True,
                action_type=ActionType.TAP,
                data={"x": point.x, "y": point.y}
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.TAP,
                error=str(e)
            )

    async def swipe(self, start: Point, end: Point, duration_ms: int = 500) -> ActionResult:
        """Swipe from start point to end point."""
        if not await self.is_connected():
            return ActionResult(
                success=False,
                action_type=ActionType.SWIPE,
                error="Device not connected"
            )

        try:
            duration_sec = duration_ms / 1000.0
            self._u2_device.swipe(
                start.x, start.y,
                end.x, end.y,
                duration=duration_sec
            )
            await asyncio.sleep(0.3)

            return ActionResult(
                success=True,
                action_type=ActionType.SWIPE,
                data={
                    "start": {"x": start.x, "y": start.y},
                    "end": {"x": end.x, "y": end.y},
                    "duration_ms": duration_ms
                }
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.SWIPE,
                error=str(e)
            )

    async def input_text(self, text: str) -> ActionResult:
        """Input text at current focus."""
        if not await self.is_connected():
            return ActionResult(
                success=False,
                action_type=ActionType.INPUT_TEXT,
                error="Device not connected"
            )

        try:
            print(f"[AndroidController] 输入文本: '{text}'")
            
            # 使用 set_fastinput_ime 确保使用正确的输入法
            self._u2_device.set_fastinput_ime(True)
            await asyncio.sleep(0.1)
            
            # 发送文本，不清空（避免焦点问题导致的 clearText 错误）
            try:
                self._u2_device.send_keys(text, clear=True)
            except Exception as clear_err:
                # 如果清空失败，尝试不清空直接输入
                print(f"[AndroidController] 清空失败，尝试直接输入: {clear_err}")
                self._u2_device.send_keys(text, clear=False)
            
            await asyncio.sleep(0.3)
            
            # 关闭快速输入法
            self._u2_device.set_fastinput_ime(False)
            
            print(f"[AndroidController] 输入完成: '{text}'")

            return ActionResult(
                success=True,
                action_type=ActionType.INPUT_TEXT,
                data={"text": text}
            )

        except Exception as e:
            print(f"[AndroidController] 输入失败: {e}")
            return ActionResult(
                success=False,
                action_type=ActionType.INPUT_TEXT,
                error=str(e)
            )

    async def press_key(self, key: str) -> ActionResult:
        """Press a specific key."""
        if not await self.is_connected():
            return ActionResult(
                success=False,
                action_type=ActionType.PRESS_KEY,
                error="Device not connected"
            )

        key_map = {
            "BACK": "back",
            "HOME": "home",
            "ENTER": "enter",
            "MENU": "menu",
            "RECENT": "recent",
            "VOLUME_UP": "volume_up",
            "VOLUME_DOWN": "volume_down",
            "POWER": "power"
        }

        try:
            u2_key = key_map.get(key.upper(), key.lower())
            self._u2_device.press(u2_key)
            await asyncio.sleep(0.3)

            return ActionResult(
                success=True,
                action_type=ActionType.PRESS_KEY,
                data={"key": key}
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.PRESS_KEY,
                error=str(e)
            )

    async def find_elements(self, selector: ElementSelector) -> list[UIElement]:
        """Find UI elements matching the selector."""
        if not await self.is_connected():
            return []

        elements: list[UIElement] = []

        try:
            # Build selector
            u2_selector = self._build_u2_selector(selector)
            if not u2_selector:
                return []

            # Find elements
            found = self._u2_device(**u2_selector)

            for i in range(found.count):
                elem = found[i]
                info = elem.info

                bounds = info.get("bounds", {})
                top_left = Point(bounds.get("left", 0), bounds.get("top", 0))
                bottom_right = Point(bounds.get("right", 0), bounds.get("bottom", 0))

                ui_element = UIElement(
                    id=info.get("resourceId"),
                    text=info.get("text"),
                    content_desc=info.get("contentDescription"),
                    class_name=info.get("className"),
                    bounds=(top_left, bottom_right),
                    clickable=info.get("clickable", False),
                    scrollable=info.get("scrollable", False),
                    enabled=info.get("enabled", True),
                    visible=info.get("visibleBounds") is not None
                )
                elements.append(ui_element)

        except Exception:
            pass

        return elements

    async def wait_for_element(
        self,
        selector: ElementSelector,
        timeout_ms: int = 5000
    ) -> UIElement | None:
        """Wait for an element to appear."""
        if not await self.is_connected():
            return None

        try:
            u2_selector = self._build_u2_selector(selector)
            if not u2_selector:
                return None

            timeout_sec = timeout_ms / 1000.0
            elem = self._u2_device(**u2_selector)

            if elem.wait(timeout=timeout_sec):
                info = elem.info
                bounds = info.get("bounds", {})
                top_left = Point(bounds.get("left", 0), bounds.get("top", 0))
                bottom_right = Point(bounds.get("right", 0), bounds.get("bottom", 0))

                return UIElement(
                    id=info.get("resourceId"),
                    text=info.get("text"),
                    content_desc=info.get("contentDescription"),
                    class_name=info.get("className"),
                    bounds=(top_left, bottom_right),
                    clickable=info.get("clickable", False),
                    scrollable=info.get("scrollable", False),
                    enabled=info.get("enabled", True)
                )

        except Exception:
            pass

        return None

    def _build_u2_selector(self, selector: ElementSelector) -> dict[str, Any]:
        """Build UIAutomator2 selector from ElementSelector."""
        u2_selector: dict[str, Any] = {}

        if selector.text:
            u2_selector["text"] = selector.text
        if selector.content_desc:
            u2_selector["description"] = selector.content_desc
        if selector.class_name:
            u2_selector["className"] = selector.class_name
        if selector.resource_id:
            u2_selector["resourceId"] = selector.resource_id

        return u2_selector

    async def get_ui_hierarchy(self, save_xml: bool = False) -> list[dict[str, Any]]:
        """Get the full UI hierarchy as a list of elements."""
        if not await self.is_connected():
            return []

        elements: list[dict[str, Any]] = []

        try:
            # Get XML hierarchy - 使用 compressed=False 获取完整层级
            # 使用 all=True 尝试获取所有窗口（包括浮层/弹窗）
            try:
                xml_content = self._u2_device.dump_hierarchy(compressed=False)
            except Exception:
                # 如果失败，回退到默认方式
                xml_content = self._u2_device.dump_hierarchy()
            
            # 调试：保存原始XML
            if save_xml:
                with open("ui_hierarchy.xml", "w", encoding="utf-8") as f:
                    f.write(xml_content)
                print(f"[UI] XML已保存到 ui_hierarchy.xml")

            # Parse XML to extract elements
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_content)

            def parse_node(node: ET.Element) -> None:
                bounds_str = node.get("bounds", "[0,0][0,0]")
                # Parse bounds string like "[0,0][100,100]"
                import re
                match = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
                if len(match) >= 2:
                    left, top = int(match[0][0]), int(match[0][1])
                    right, bottom = int(match[1][0]), int(match[1][1])
                    center = ((left + right) // 2, (top + bottom) // 2)
                else:
                    left = top = right = bottom = 0
                    center = (0, 0)

                elem = {
                    "id": node.get("resource-id"),
                    "text": node.get("text"),
                    "content_desc": node.get("content-desc"),
                    "class_name": node.get("class"),
                    "bounds": (left, top, right, bottom),
                    "center": center,
                    "clickable": node.get("clickable") == "true",
                    "scrollable": node.get("scrollable") == "true",
                    "enabled": node.get("enabled") == "true",
                    "visible": True
                }

                # 添加有标识信息的元素，或者可点击的元素，或者输入框
                has_identity = elem["text"] or elem["content_desc"] or elem["id"]
                is_interactive = elem["clickable"] and (right - left) > 10 and (bottom - top) > 10
                class_lower = (elem["class_name"] or "").lower()
                is_input = "edittext" in class_lower or "input" in class_lower
                
                if has_identity or is_interactive or is_input:
                    elements.append(elem)

                for child in node:
                    parse_node(child)

            parse_node(root)

        except Exception:
            pass

        return elements

    async def launch_app(self, package_name: str) -> ActionResult:
        """Launch an app by package name."""
        if not await self.is_connected():
            return ActionResult(
                success=False,
                action_type=ActionType.TAP,
                error="Device not connected"
            )

        try:
            self._u2_device.app_start(package_name)
            await asyncio.sleep(1.0)  # Wait for app to launch

            return ActionResult(
                success=True,
                action_type=ActionType.TAP,
                data={"package": package_name, "action": "launch"}
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_type=ActionType.TAP,
                error=str(e)
            )
