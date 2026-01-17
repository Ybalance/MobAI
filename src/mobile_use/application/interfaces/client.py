"""Main client interface for Mobile-Use system."""

from abc import ABC, abstractmethod

from mobile_use.domain.entities.device import Device
from mobile_use.domain.entities.task import Task, TaskResult


class MobileUseClient(ABC):
    """Main client interface for interacting with the Mobile-Use system.
    
    This is the primary entry point for users to interact with the system,
    providing high-level methods for device control and task execution.
    """
    
    @abstractmethod
    async def connect_device(self, platform: str, device_id: str | None = None) -> Device:
        """Connect to a mobile device.
        
        Args:
            platform: Device platform ('android' or 'ios')
            device_id: Optional specific device ID to connect to
            
        Returns:
            Connected Device instance
            
        Raises:
            DeviceConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    async def disconnect_device(self, device_id: str) -> None:
        """Disconnect from a device.
        
        Args:
            device_id: ID of device to disconnect
        """
        pass
    
    @abstractmethod
    async def list_devices(self) -> list[Device]:
        """List all available devices.
        
        Returns:
            List of available Device instances
        """
        pass
    
    @abstractmethod
    async def execute_task(self, instruction: str, device_id: str | None = None) -> TaskResult:
        """Execute a natural language task on a device.
        
        Args:
            instruction: Natural language instruction
            device_id: Optional device ID (uses default if not specified)
            
        Returns:
            TaskResult with execution details
            
        Raises:
            TaskExecutionError: If task execution fails
        """
        pass
    
    @abstractmethod
    async def get_task_status(self, task_id: str) -> Task:
        """Get status of a running task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            Task instance with current status
        """
        pass
    
    @abstractmethod
    async def cancel_task(self, task_id: str) -> None:
        """Cancel a running task.
        
        Args:
            task_id: ID of the task to cancel
        """
        pass
