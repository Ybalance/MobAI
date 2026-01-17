"""Device repository interface."""

from abc import ABC, abstractmethod

from mobile_use.domain.entities.device import Device


class DeviceRepository(ABC):
    """Repository interface for device persistence."""
    
    @abstractmethod
    async def save(self, device: Device) -> Device:
        """Save a device."""
        pass
    
    @abstractmethod
    async def find_by_id(self, device_id: str) -> Device | None:
        """Find device by ID."""
        pass
    
    @abstractmethod
    async def find_by_device_id(self, device_id: str) -> Device | None:
        """Find device by platform device ID."""
        pass
    
    @abstractmethod
    async def find_all(self) -> list[Device]:
        """Find all devices."""
        pass
    
    @abstractmethod
    async def delete(self, device_id: str) -> None:
        """Delete a device."""
        pass
