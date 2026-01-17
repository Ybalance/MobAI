"""Point value object for representing coordinates."""

import math
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class Point:
    """Immutable point representing x, y coordinates on a screen.
    
    This value object is used throughout the system to represent
    positions for UI element locations, touch coordinates, etc.
    """
    
    x: int
    y: int
    
    def __post_init__(self) -> None:
        """Validate point coordinates."""
        if self.x < 0 or self.y < 0:
            raise ValueError("Point coordinates must be non-negative")
    
    def distance_to(self, other: Self) -> float:
        """Calculate Euclidean distance to another point.
        
        Args:
            other: Another Point instance
            
        Returns:
            Distance as a float
        """
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
    
    def offset(self, dx: int, dy: int) -> Self:
        """Create a new point offset by the given deltas.
        
        Args:
            dx: X offset
            dy: Y offset
            
        Returns:
            New Point instance
        """
        return Point(self.x + dx, self.y + dy)
    
    def is_within_bounds(self, width: int, height: int) -> bool:
        """Check if point is within given bounds.
        
        Args:
            width: Maximum width
            height: Maximum height
            
        Returns:
            True if point is within bounds
        """
        return 0 <= self.x < width and 0 <= self.y < height
    
    def __str__(self) -> str:
        """String representation of the point."""
        return f"Point({self.x}, {self.y})"
