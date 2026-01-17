"""Device entity representing mobile devices."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from mobile_use.domain.value_objects.screen_info import ScreenInfo


class DevicePlatform(Enum):
    """Supported device platforms."""
    ANDROID = "android"
    IOS = "ios"


class DeviceStatus(Enum):
    """Device connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class Device:
    """Device entity representing a mobile device."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    platform: DevicePlatform = DevicePlatform.ANDROID
    platform_version: str = ""
    device_id: str = ""
    model: str = ""
    manufacturer: str = ""
    status: DeviceStatus = DeviceStatus.DISCONNECTED
    screen_info: ScreenInfo | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_seen: datetime | None = None
    connected_at: datetime | None = None
    
    def connect(self) -> None:
        """Mark device as connected."""
        self.status = DeviceStatus.CONNECTED
        self.connected_at = datetime.now()
        self.last_seen = datetime.now()
    
    def disconnect(self) -> None:
        """Mark device as disconnected."""
        self.status = DeviceStatus.DISCONNECTED
        self.last_seen = datetime.now()
    
    def update_last_seen(self) -> None:
        """Update last seen timestamp."""
        self.last_seen = datetime.now()
    
    def set_error(self) -> None:
        """Mark device as having an error."""
        self.status = DeviceStatus.ERROR
        self.last_seen = datetime.now()
    
    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self.status == DeviceStatus.CONNECTED
    
    @property
    def is_android(self) -> bool:
        """Check if device is Android."""
        return self.platform == DevicePlatform.ANDROID
    
    @property
    def is_ios(self) -> bool:
        """Check if device is iOS."""
        return self.platform == DevicePlatform.IOS
    
    @property
    def display_name(self) -> str:
        """Get display name for the device."""
        if self.name:
            return self.name
        if self.model and self.manufacturer:
            return f"{self.manufacturer} {self.model}"
        return self.device_id or self.id
    
    def __str__(self) -> str:
        """String representation of the device."""
        return f"Device({self.display_name}, {self.platform.value}, {self.status.value})"
