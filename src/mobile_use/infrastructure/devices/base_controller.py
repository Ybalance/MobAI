"""Base device controller interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mobile_use.domain.entities.device import Device
from mobile_use.domain.value_objects.point import Point
from mobile_use.domain.value_objects.screen_info import ScreenInfo


class ActionType(Enum):
    """Types of device actions."""
    TAP = "tap"
    SWIPE = "swipe"
    INPUT_TEXT = "input_text"
    PRESS_KEY = "press_key"
    LONG_PRESS = "long_press"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"


@dataclass
class ActionResult:
    """Result of a device action."""
    success: bool
    action_type: ActionType
    data: dict[str, Any] | None = None
    error: str | None = None
    screenshot_path: str | None = None
    duration_ms: int | None = None


@dataclass
class UIElement:
    """UI element representation."""
    id: str | None = None
    text: str | None = None
    content_desc: str | None = None
    class_name: str | None = None
    bounds: tuple[Point, Point] | None = None
    clickable: bool = False
    scrollable: bool = False
    enabled: bool = True
    visible: bool = True
    attributes: dict[str, Any] | None = None

    @property
    def center(self) -> Point | None:
        """Get center point of the element."""
        if self.bounds:
            top_left, bottom_right = self.bounds
            return Point(
                (top_left.x + bottom_right.x) // 2,
                (top_left.y + bottom_right.y) // 2
            )
        return None


@dataclass
class ElementSelector:
    """Selector for finding UI elements."""
    text: str | None = None
    content_desc: str | None = None
    class_name: str | None = None
    resource_id: str | None = None
    xpath: str | None = None
    index: int | None = None


class DeviceController(ABC):
    """Abstract base class for device controllers.
    
    This defines the unified interface for controlling different mobile platforms.
    All platform-specific controllers must implement these methods.
    """
    
    def __init__(self, device: Device):
        self.device = device
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the device.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        pass
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if device is connected."""
        pass
    
    @abstractmethod
    async def get_screen_info(self) -> ScreenInfo:
        """Get current screen information."""
        pass
    
    @abstractmethod
    async def take_screenshot(self, save_path: str | None = None) -> ActionResult:
        """Take a screenshot of the device screen.
        
        Args:
            save_path: Optional path to save screenshot
            
        Returns:
            ActionResult with screenshot data
        """
        pass
    
    @abstractmethod
    async def tap(self, point: Point) -> ActionResult:
        """Tap at the specified point.
        
        Args:
            point: Point to tap
            
        Returns:
            ActionResult indicating success/failure
        """
        pass
    
    @abstractmethod
    async def swipe(self, start: Point, end: Point, duration_ms: int = 500) -> ActionResult:
        """Swipe from start point to end point.
        
        Args:
            start: Starting point
            end: Ending point
            duration_ms: Duration of swipe in milliseconds
            
        Returns:
            ActionResult indicating success/failure
        """
        pass
    
    @abstractmethod
    async def input_text(self, text: str) -> ActionResult:
        """Input text at current focus.
        
        Args:
            text: Text to input
            
        Returns:
            ActionResult indicating success/failure
        """
        pass
    
    @abstractmethod
    async def press_key(self, key: str) -> ActionResult:
        """Press a specific key.
        
        Args:
            key: Key to press (e.g., 'BACK', 'HOME', 'ENTER')
            
        Returns:
            ActionResult indicating success/failure
        """
        pass
    
    @abstractmethod
    async def find_elements(self, selector: ElementSelector) -> list[UIElement]:
        """Find UI elements matching the selector.
        
        Args:
            selector: Element selector criteria
            
        Returns:
            List of matching UIElement objects
        """
        pass
    
    @abstractmethod
    async def wait_for_element(self, selector: ElementSelector, timeout_ms: int = 5000) -> UIElement | None:
        """Wait for an element to appear.
        
        Args:
            selector: Element selector criteria
            timeout_ms: Timeout in milliseconds
            
        Returns:
            UIElement if found, None if timeout
        """
        pass
    
    async def tap_element(self, selector: ElementSelector) -> ActionResult:
        """Tap on an element matching the selector.
        
        Args:
            selector: Element selector criteria
            
        Returns:
            ActionResult indicating success/failure
        """
        elements = await self.find_elements(selector)
        if not elements:
            return ActionResult(
                success=False,
                action_type=ActionType.TAP,
                error="Element not found"
            )
        
        element = elements[0]
        if element.center:
            return await self.tap(element.center)
        else:
            return ActionResult(
                success=False,
                action_type=ActionType.TAP,
                error="Element has no bounds"
            )
