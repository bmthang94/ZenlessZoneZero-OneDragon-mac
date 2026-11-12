import os

import ApplicationServices as AS
import Quartz
from AppKit import (
    NSApplicationActivateIgnoringOtherApps,
    NSRunningApplication,
    NSWorkspace,
)

from one_dragon.base.geometry.point import Point
from one_dragon.base.geometry.rectangle import Rect
from one_dragon.utils.log_utils import log


class MacGameWindowHandle:
    """macOS 游戏窗口的进程句柄。"""

    def __init__(self, window_id: int, owner_pid: int, title: str):
        self.window_id: int = window_id
        self.owner_pid: int = owner_pid
        self.title: str = title

    @property
    def isActive(self) -> bool:
        """游戏窗口所属应用是否处于前台。"""
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is not None and front.processIdentifier() == self.owner_pid:
            return True
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            self.owner_pid
        )
        return app is not None and bool(app.isActive())

    def activate(self) -> bool:
        """将游戏窗口所属应用切到前台。"""
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            self.owner_pid
        )
        if app is None:
            return False
        return bool(
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        )


class MacPcGameWindow:
    """通过 macOS 窗口列表定位 PlayCover 中的游戏窗口。"""

    GAME_TITLE_ALIASES: dict[str, set[str]] = {
        '绝区零': {'绝区零', '絕區零'},
        '絕區零': {'绝区零', '絕區零'},
        'ZenlessZoneZero': {'ZenlessZoneZero', 'Zenless Zone Zero'},
        'Zenless Zone Zero': {'ZenlessZoneZero', 'Zenless Zone Zero'},
    }

    def __init__(
        self,
        standard_width: int = 1920,
        standard_height: int = 1080,
    ):
        self.win_title: str | None = None
        self.standard_width: int = standard_width
        self.standard_height: int = standard_height
        self.standard_game_rect: Rect = Rect(0, 0, standard_width, standard_height)
        self._win: MacGameWindowHandle | None = None
        self._window_id: int | None = None
        self._content_bounds_warning_logged: bool = False

    def _clear_cached_window(self) -> None:
        self._win = None
        self._window_id = None

    @staticmethod
    def _get_windows() -> list[dict]:
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        return list(windows or [])

    def init_win(self) -> None:
        """查找标题与配置相符的可见游戏窗口。"""
        if not self.win_title:
            return

        current_pid = os.getpid()
        expected_titles = self.GAME_TITLE_ALIASES.get(
            self.win_title, {self.win_title}
        )
        for window in self._get_windows():
            window_id = window.get(Quartz.kCGWindowNumber)
            owner_pid = window.get(Quartz.kCGWindowOwnerPID)
            if window_id is None or owner_pid is None:
                continue
            if int(owner_pid) == current_pid:
                continue
            if int(window.get(Quartz.kCGWindowLayer, 0)) != 0:
                continue

            title = str(window.get(Quartz.kCGWindowName, '') or '').strip()
            owner_name = str(window.get(Quartz.kCGWindowOwnerName, '') or '').strip()
            if not any(
                candidate == expected
                for expected in expected_titles
                for candidate in (title, owner_name)
            ):
                continue

            self._window_id = int(window_id)
            self._win = MacGameWindowHandle(
                self._window_id,
                int(owner_pid),
                title or owner_name,
            )
            return

        self._clear_cached_window()

    def update_win_title(self, new_title: str) -> None:
        """更新窗口标题并清除缓存。"""
        if self.win_title != new_title:
            self.win_title = new_title
            self._clear_cached_window()

    def refresh_win(self) -> None:
        self._clear_cached_window()
        self.init_win()

    def get_win(self) -> MacGameWindowHandle | None:
        if self._win is None:
            self.init_win()
        return self._win

    def get_hwnd(self) -> int | None:
        if self._window_id is None:
            self.init_win()
        return self._window_id

    @property
    def is_win_valid(self) -> bool:
        """检查缓存的游戏窗口是否仍然显示。"""
        window_id = self.get_hwnd()
        if window_id is None:
            return False
        if any(
            int(window.get(Quartz.kCGWindowNumber, -1)) == window_id
            for window in self._get_windows()
        ):
            return True
        self._clear_cached_window()
        return False

    @property
    def is_win_active(self) -> bool:
        window = self.get_win()
        return window.isActive if window is not None else False

    @property
    def window_rect(self) -> Rect | None:
        """Return the full window bounds, including the title bar, in screen points."""
        window_id = self.get_hwnd()
        if window_id is None:
            return None

        for window in self._get_windows():
            if int(window.get(Quartz.kCGWindowNumber, -1)) != window_id:
                continue
            bounds = window.get(Quartz.kCGWindowBounds, {})
            x = round(bounds.get('X', 0))
            y = round(bounds.get('Y', 0))
            width = round(bounds.get('Width', 0))
            height = round(bounds.get('Height', 0))
            if width <= 0 or height <= 0:
                return None
            return Rect(x, y, x + width, y + height)

        self._clear_cached_window()
        return None

    @staticmethod
    def _ax_attribute(element: object, name: str) -> object | None:
        error, value = AS.AXUIElementCopyAttributeValue(element, name, None)
        return value if error == 0 else None

    @classmethod
    def _ax_rect(cls, element: object) -> Rect | None:
        position = cls._ax_attribute(element, 'AXPosition')
        size = cls._ax_attribute(element, 'AXSize')
        if position is None or size is None:
            return None
        got_position, point = AS.AXValueGetValue(position, AS.kAXValueCGPointType, None)
        got_size, dimensions = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
        if not got_position or not got_size:
            return None
        if dimensions.width <= 0 or dimensions.height <= 0:
            return None
        return Rect(
            round(point.x), round(point.y),
            round(point.x + dimensions.width), round(point.y + dimensions.height),
        )

    @property
    def win_rect(self) -> Rect | None:
        """Use the same content viewport for screenshots and click coordinates."""
        outer = self.window_rect
        window = self.get_win()
        if outer is None or window is None:
            return None
        app = AS.AXUIElementCreateApplication(window.owner_pid)
        for ax_window in self._ax_attribute(app, 'AXWindows') or []:
            bounds = self._ax_rect(ax_window)
            if bounds is None or (
                bounds.x1, bounds.y1, bounds.x2, bounds.y2
            ) != (outer.x1, outer.y1, outer.x2, outer.y2):
                continue
            for child in self._ax_attribute(ax_window, 'AXChildren') or []:
                if self._ax_attribute(child, 'AXRole') != 'AXGroup':
                    continue
                content = self._ax_rect(child)
                if content is not None and (
                    content.x1 == outer.x1 and content.x2 == outer.x2
                    and content.y2 == outer.y2
                    and outer.y1 <= content.y1 < outer.y2
                ):
                    self._content_bounds_warning_logged = False
                    return content
        if not self._content_bounds_warning_logged:
            log.error(
                'Cannot determine PlayCover content bounds; '
                'check Accessibility access for the running application'
            )
            self._content_bounds_warning_logged = True
        return None

    @property
    def is_win_scale(self) -> bool:
        rect = self.win_rect
        return rect is not None and (
            rect.width != self.standard_width or rect.height != self.standard_height
        )

    def active(self) -> bool:
        window = self.get_win()
        if window is None:
            return False
        if window.isActive:
            return True
        if not window.activate():
            log.error('无法激活 PlayCover 游戏窗口，请检查系统辅助功能权限')
            return False
        return True

    def get_scaled_game_pos(self, game_pos: Point) -> Point | None:
        rect = self.win_rect
        if rect is None:
            return None
        xs = rect.width / self.standard_width
        ys = rect.height / self.standard_height
        scaled_pos = Point(game_pos.x * xs, game_pos.y * ys)
        return (
            scaled_pos
            if self.is_valid_game_pos(game_pos, self.standard_game_rect)
            else None
        )

    @staticmethod
    def is_valid_game_pos(s_pos: Point, rect: Rect | None = None) -> bool:
        if rect is None:
            return s_pos.x >= 0 and s_pos.y >= 0
        return 0 <= s_pos.x < rect.width and 0 <= s_pos.y < rect.height

    def game2win_pos(self, game_pos: Point) -> Point | None:
        rect = self.win_rect
        if rect is None or not self.is_valid_game_pos(game_pos, self.standard_game_rect):
            return None
        scaled_pos = Point(
            game_pos.x * rect.width / self.standard_width,
            game_pos.y * rect.height / self.standard_height,
        )
        return rect.left_top + scaled_pos
