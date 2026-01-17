"""Screen information value object."""

from dataclasses import dataclass
from typing import Optional

from mobile_use.domain.value_objects.point import Point


@dataclass(frozen=True)
class ScreenInfo:
    """Immutable screen information containing dimensions and properties.
    
    This value object encapsulates all relevant screen information
    needed for device automation and UI element positioning.
    """
    
    width: int
    height: int
    density: float
    orientation: str
    scale_factor: float = 1.0
    
    def __post_init__(self) -> None:
        """Validate screen information."""
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Screen dimensions must be positive")
        if self.density <= 0:
            raise ValueError("Screen density must be positive")
        if self.scale_factor <= 0:
            raise ValueError("Scale factor must be positive")
        if self.orientation not in ("portrait", "landscape"):
            raise ValueError("Orientation must be 'portrait' or 'landscape'")
    
    @property
    def center(self) -> Point:
        """Get the center point of the screen."""
        return Point(self.width // 2, self.height // 2)
    
    @property
    def aspect_ratio(self) -> float:
        """Calculate the aspect ratio (width/height)."""
        return self.width / self.height
    
    @property
    def is_portrait(self) -> bool:
        """Check if screen is in portrait orientation."""
        return self.orientation == "portrait"
    
    @property
    def is_landscape(self) -> bool:
        """Check if screen is in landscape orientation."""
        return self.orientation == "landscape"
    
    def contains_point(self, point: Point) -> bool:
        """Check if a point is within screen bounds."""
        return point.is_within_bounds(self.width, self.height)
    
    def scale_point(self, point: Point) -> Point:
        """Scale a point according to screen scale factor."""
        return Point(
            int(point.x * self.scale_factor),
            int(point.y * self.scale_factor)
        )
    
    def get_safe_area(self, margin: int = 50) -> tuple[Point, Point]:
        """Get safe area coordinates with margin from edges.
        
        Args:
            margin: Margin from screen edges in pixels
            
        Returns:
            Tuple of (top_left, bottom_right) points defining safe area
        """
        top_left = Point(margin, margin)
        bottom_right = Point(self.width - margin, self.height - margin)
        return top_left, bottom_right
    
    def __str__(self) -> str:
        """String representation of screen info."""
        return (
            f"ScreenInfo({self.width}x{self.height}, "
            f"density={self.density}, orientation={self.orientation})"
        )
