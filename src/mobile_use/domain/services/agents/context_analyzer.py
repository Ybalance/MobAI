"""Context Analyzer Agent - Analyzes screen state and UI elements."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from mobile_use.domain.services.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
)


class VisionProvider(Protocol):
    """Protocol for vision/image analysis providers."""
    async def analyze_image(self, image: bytes, prompt: str) -> str:
        """Analyze an image with a prompt."""
        ...


@dataclass
class UIElementInfo:
    """Information about a UI element."""
    id: str | None = None
    text: str | None = None
    content_desc: str | None = None
    class_name: str | None = None
    bounds: tuple[int, int, int, int] | None = None
    center: tuple[int, int] | None = None
    clickable: bool = False
    scrollable: bool = False
    enabled: bool = True
    visible: bool = True
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "content_desc": self.content_desc,
            "class_name": self.class_name,
            "bounds": self.bounds,
            "center": self.center,
            "clickable": self.clickable,
            "scrollable": self.scrollable,
            "enabled": self.enabled,
            "visible": self.visible,
            "confidence": self.confidence
        }


@dataclass
class ScreenAnalysis:
    """Complete screen analysis result."""
    app_name: str | None = None
    activity_name: str | None = None
    screen_type: str | None = None
    elements: list[UIElementInfo] = field(default_factory=list)
    text_content: list[str] = field(default_factory=list)
    interactive_elements: list[UIElementInfo] = field(default_factory=list)
    scroll_direction: str | None = None
    has_keyboard: bool = False
    has_dialog: bool = False
    confidence: float = 1.0

    def find_element_by_text(self, text: str) -> UIElementInfo | None:
        """Find element by text content."""
        text_lower = text.lower()
        for element in self.elements:
            if element.text and text_lower in element.text.lower():
                return element
            if element.content_desc and text_lower in element.content_desc.lower():
                return element
        return None

    def find_clickable_elements(self) -> list[UIElementInfo]:
        """Get all clickable elements."""
        return [e for e in self.elements if e.clickable and e.enabled]


class ContextAnalyzerAgent(BaseAgent):
    """Agent responsible for analyzing screen context.

    This agent examines the current screen state, identifies UI elements,
    and provides contextual information for decision making.
    """

    def __init__(self, vision_provider: VisionProvider | None = None):
        super().__init__(
            name="ContextAnalyzer",
            description="Analyzes screen state and identifies UI elements"
        )
        self.vision_provider = vision_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute screen analysis.

        Args:
            context: Current execution context with screenshot

        Returns:
            AgentResult containing screen analysis
        """
        analysis = ScreenAnalysis()

        # Analyze UI elements from context
        if context.ui_elements:
            analysis = self._analyze_ui_hierarchy(context.ui_elements)

        # Use vision model if available and screenshot provided
        if self.vision_provider and context.screenshot:
            vision_analysis = await self._analyze_with_vision(
                context.screenshot,
                context.instruction
            )
            analysis = self._merge_analysis(analysis, vision_analysis)

        # Extract screen info
        if context.screen_info:
            analysis.app_name = context.screen_info.get("app_name")
            analysis.activity_name = context.screen_info.get("activity_name")

        return AgentResult.success_result(
            message=f"Analyzed screen with {len(analysis.elements)} elements",
            data={
                "analysis": {
                    "app_name": analysis.app_name,
                    "activity_name": analysis.activity_name,
                    "screen_type": analysis.screen_type,
                    "element_count": len(analysis.elements),
                    "interactive_count": len(analysis.interactive_elements),
                    "text_content": analysis.text_content[:10],
                    "has_keyboard": analysis.has_keyboard,
                    "has_dialog": analysis.has_dialog,
                    "confidence": analysis.confidence
                },
                "elements": [e.to_dict() for e in analysis.elements[:50]],
                "interactive_elements": [
                    e.to_dict() for e in analysis.interactive_elements[:20]
                ]
            },
            confidence=analysis.confidence
        )

    def _analyze_ui_hierarchy(self, ui_elements: list[dict[str, Any]]) -> ScreenAnalysis:
        """Analyze UI hierarchy from device."""
        analysis = ScreenAnalysis()

        for elem_data in ui_elements:
            element = UIElementInfo(
                id=elem_data.get("id"),
                text=elem_data.get("text"),
                content_desc=elem_data.get("content_desc"),
                class_name=elem_data.get("class_name"),
                bounds=elem_data.get("bounds"),
                center=elem_data.get("center"),
                clickable=elem_data.get("clickable", False),
                scrollable=elem_data.get("scrollable", False),
                enabled=elem_data.get("enabled", True),
                visible=elem_data.get("visible", True)
            )
            analysis.elements.append(element)

            if element.text:
                analysis.text_content.append(element.text)

            if element.clickable and element.enabled:
                analysis.interactive_elements.append(element)

            # Detect keyboard
            if element.class_name and "keyboard" in element.class_name.lower():
                analysis.has_keyboard = True

            # Detect dialog
            if element.class_name and "dialog" in element.class_name.lower():
                analysis.has_dialog = True

        return analysis

    async def _analyze_with_vision(
        self,
        screenshot: bytes,
        instruction: str
    ) -> ScreenAnalysis:
        """Analyze screenshot using vision model."""
        import json

        prompt = f"""Analyze this mobile screen screenshot.
User wants to: {instruction}

Identify:
1. What app is this?
2. What type of screen is this (home, list, detail, form, etc)?
3. Key interactive elements visible
4. Any text content visible
5. Is there a keyboard visible?
6. Is there a dialog/popup visible?

Return JSON:
{{
    "app_name": "string or null",
    "screen_type": "string",
    "elements": [
        {{"text": "string", "type": "button|input|text|image", "clickable": bool}}
    ],
    "text_content": ["visible text strings"],
    "has_keyboard": bool,
    "has_dialog": bool,
    "confidence": 0.0-1.0
}}"""

        try:
            response = await self.vision_provider.analyze_image(screenshot, prompt)  # type: ignore
            data = json.loads(response)

            analysis = ScreenAnalysis(
                app_name=data.get("app_name"),
                screen_type=data.get("screen_type"),
                has_keyboard=data.get("has_keyboard", False),
                has_dialog=data.get("has_dialog", False),
                confidence=data.get("confidence", 0.7)
            )

            for elem in data.get("elements", []):
                analysis.elements.append(UIElementInfo(
                    text=elem.get("text"),
                    class_name=elem.get("type"),
                    clickable=elem.get("clickable", False)
                ))

            analysis.text_content = data.get("text_content", [])
            return analysis

        except Exception:
            return ScreenAnalysis(confidence=0.3)

    def _merge_analysis(
        self,
        hierarchy_analysis: ScreenAnalysis,
        vision_analysis: ScreenAnalysis
    ) -> ScreenAnalysis:
        """Merge analysis from UI hierarchy and vision model."""
        merged = ScreenAnalysis(
            app_name=hierarchy_analysis.app_name or vision_analysis.app_name,
            activity_name=hierarchy_analysis.activity_name,
            screen_type=vision_analysis.screen_type,
            elements=hierarchy_analysis.elements,
            text_content=list(set(
                hierarchy_analysis.text_content + vision_analysis.text_content
            )),
            interactive_elements=hierarchy_analysis.interactive_elements,
            has_keyboard=hierarchy_analysis.has_keyboard or vision_analysis.has_keyboard,
            has_dialog=hierarchy_analysis.has_dialog or vision_analysis.has_dialog,
            confidence=(hierarchy_analysis.confidence + vision_analysis.confidence) / 2
        )
        return merged
