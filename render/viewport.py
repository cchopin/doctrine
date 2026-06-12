"""Scrollable window over the map, independent from curses."""
from __future__ import annotations


class Viewport:
    def __init__(self, map_width: int, map_height: int):
        self.map_width = map_width
        self.map_height = map_height
        self.x = 0
        self.y = 0
        self.width = 1
        self.height = 1

    def resize(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self._clamp()

    def move(self, dx: int, dy: int) -> None:
        self.x += dx
        self.y += dy
        self._clamp()

    def center_on(self, x: int, y: int) -> None:
        self.x = x - self.width // 2
        self.y = y - self.height // 2
        self._clamp()

    def _clamp(self) -> None:
        self.x = max(0, min(self.x, self.map_width - self.width))
        self.y = max(0, min(self.y, self.map_height - self.height))

    def contains(self, x: int, y: int) -> bool:
        return (
            self.x <= x < self.x + self.width
            and self.y <= y < self.y + self.height
        )
