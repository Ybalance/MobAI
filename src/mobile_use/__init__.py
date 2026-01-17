"""
Mobile-Use v2.0 - AI-Driven Mobile Device Automation System

A sophisticated automation platform that uses Large Language Models (LLMs)
to understand natural language instructions and control mobile devices intelligently.

This package provides:
- Cross-platform device control (Android & iOS)
- AI-powered UI element recognition
- Natural language task processing
- Intelligent error recovery
- Extensible plugin system
"""

__version__ = "2.0.0"
__author__ = "Mobile-Use Team"
__email__ = "team@mobile-use.com"
__license__ = "MIT"

from mobile_use.application.interfaces.client import MobileUseClient
from mobile_use.domain.entities.device import Device
from mobile_use.domain.entities.task import Task, TaskResult
from mobile_use.domain.value_objects.point import Point
from mobile_use.domain.value_objects.screen_info import ScreenInfo

__all__ = [
    "MobileUseClient",
    "Task",
    "TaskResult",
    "Device",
    "Point",
    "ScreenInfo",
]
