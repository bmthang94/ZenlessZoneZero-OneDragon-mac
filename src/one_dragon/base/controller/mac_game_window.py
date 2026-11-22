import os
import subprocess
import time

import ApplicationServices as AS
import Quartz
from AppKit import (
    NSApplicationActivateIgnoringOtherApps,
    NSRunningApplication,
    NSWorkspace,
)
from CoreFoundation import kCFBooleanTrue

from one_dragon.base.geometry.point import Point
from one_dragon.base.geometry.rectangle import Rect
from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log


class MacGameWindowHandle:
    """macOS 游戏窗口的进程句柄。"""

    def __init__(self, window_id: int, owner_pid: int, title: str) -> None:
        self.window_id: int = window_id
        self.owner_pid: int = owner_pid
        self.title: str = title

    def _is_frontmost(self) -> bool:
        """游戏窗口所属进程当前是否是系统前台应用。"""
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        return front is not None and front.processIdentifier() == self.owner_pid

    @property
    def isActive(self) -> bool:
        """游戏窗口所属应用是否处于前台。"""
        if self._is_frontmost():
            return True
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            self.owner_pid
        )
        return app is not None and bool(app.isActive())

    def _wait_frontmost(self, timeout: float = 0.15) -> bool:
        """轮询等待进程成为前台应用；激活是异步的，立即查可能拿到旧状态。"""
        deadline = time.monotonic() + timeout
        while True:
            if self._is_frontmost():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    def _activate_via_system_events(self) -> bool:
        """通过 AppleScript System Events 把进程切到前台。

        进程从后台（如 MCP server 子进程）调用 activateWithOptions_ 时，
        macOS 的焦点窃取防护会让命令返回 True 但实际不切换 frontmost，
        需要 System Events 的 frontmost 赋值作为兜底。
        """
        script = (
            'tell application "System Events" to '
            f'set frontmost of (first process whose unix id is {self.owner_pid}) to true'
        )
        try:
            result = subprocess.run(
                ['/usr/bin/osascript', '-e', script],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as e:
            log.warning(gt('osascript 激活游戏窗口失败: %(v)s', model='log'), {'v': e})
            return False
        if result.returncode != 0:
            log.warning(
                gt('osascript 激活游戏窗口失败: %(v)s', model='log'),
                {'v': result.stderr.strip()},
            )
            return False
        return self._is_frontmost()

    def activate(self) -> bool:
        """将游戏窗口所属应用切到前台，并确认 frontmost 真的切换了。"""
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            self.owner_pid
        )
        if app is None:
            return False
        if app.isHidden():
            app.unhide()
        if app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps) and self._wait_frontmost():
            return True
        # 旧接口在部分 macOS 版本上可能失败，退回到不带选项的 activate
        activate = getattr(app, 'activate', None)
        if activate is not None and activate() and self._wait_frontmost():
            return True
        if self._activate_via_bundle_url(app):
            return True
        return self._activate_via_system_events()

    def _activate_via_bundle_url(self, app: NSRunningApplication) -> bool:
        """通过 /usr/bin/open 打开 app bundle 将容器应用拉到前台。"""
        get_bundle = getattr(app, 'bundleURL', None)
        bundle_url = get_bundle() if callable(get_bundle) else None
        if bundle_url is None:
            return False
        bundle_path = getattr(bundle_url, 'path', None)
        path_str = bundle_path() if callable(bundle_path) else str(bundle_url)
        if not path_str:
            return False
        try:
            res = subprocess.run(['/usr/bin/open', path_str], capture_output=True, timeout=5)
            if res.returncode == 0 and self._wait_frontmost():
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        return False

    def close(self) -> None:
        """关闭游戏窗口所属应用。"""
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            self.owner_pid
        )
        if app is None:
            return
        app.terminate()
        for _ in range(10):
            if app.isTerminated():
                return
            time.sleep(0.1)
        if not app.forceTerminate() and not app.isTerminated():
            raise RuntimeError(gt('无法关闭 PlayCover 游戏', model='log'))


class MacPcGameWindow:
    """通过 macOS 窗口列表定位 PlayCover 中的游戏窗口。"""

    GAME_TITLE_ALIASES: frozenset[str] = frozenset({
        '绝区零', '絕區零', 'ZenlessZoneZero', 'Zenless Zone Zero',
    })
    def __init__(
        self,
        standard_width: int = 1920,
        standard_height: int = 1080,
    ) -> None:
        self.win_title: str | None = None
        self.standard_width: int = standard_width
        self.standard_height: int = standard_height
        self.standard_game_rect: Rect = Rect(0, 0, standard_width, standard_height)
        self._win: MacGameWindowHandle | None = None
        self._window_id: int | None = None
        self._content_bounds_warning_logged: bool = False
        self._activate_error_logged: bool = False

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
        expected_titles = (
            self.GAME_TITLE_ALIASES if self.win_title in self.GAME_TITLE_ALIASES
            else {self.win_title}
        )
        matched_window: MacGameWindowHandle | None = None
        best_rank: tuple[int, float] = (0, 0)
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
            if title not in expected_titles and owner_name not in expected_titles:
                continue

            if title == self.win_title:
                rank = (4, 0)
            elif title in expected_titles:
                rank = (3, 0)
            else:
                # 应用所属的小窗口可能排在游戏窗口之前，按标题找不到时优先选择较大的窗口。
                bounds = window.get(Quartz.kCGWindowBounds, {})
                area = bounds.get('Width', 0) * bounds.get('Height', 0)
                rank = (2 if owner_name == self.win_title else 1, area)
            if rank > best_rank:
                matched_window = MacGameWindowHandle(int(window_id), int(owner_pid), title or owner_name)
                best_rank = rank

        if matched_window is None:
            self._clear_cached_window()
        else:
            self._win = matched_window
            self._window_id = matched_window.window_id

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
        if window_id is None or self._win is None:
            return False
        if any(
            int(window.get(Quartz.kCGWindowNumber, -1)) == window_id
            and int(window.get(Quartz.kCGWindowOwnerPID, -1)) == self._win.owner_pid
            for window in self._get_windows()
        ):
            return True
        self._clear_cached_window()
        return False

    @property
    def is_win_active(self) -> bool:
        """游戏窗口是否处于可接收输入的前台状态。

        除了要求所属应用在前台，还要求目标窗口是该应用的焦点窗口；
        PlayCover 可能有多个窗口，应用前台但焦点在别的窗口时键盘输入会落空。
        AX 查询不可用（未授予辅助功能权限）时退回应用级判断。
        """
        window = self.get_win()
        if window is None or not window.isActive:
            return False
        focused_is_target = self._focused_window_is_target(window)
        return True if focused_is_target is None else focused_is_target

    def _focused_window_is_target(self, window: MacGameWindowHandle) -> bool | None:
        """前台应用的焦点窗口是否就是目标游戏窗口；无法判定时返回 None。

        Args:
            window: 目标游戏窗口句柄

        Returns:
            焦点窗口与目标窗口一致返回 True，不一致返回 False，无法判定返回 None
        """
        outer = self.window_rect
        if outer is None:
            return None
        app = AS.AXUIElementCreateApplication(window.owner_pid)
        focused = self._ax_attribute(app, 'AXFocusedWindow')
        if focused is None:
            focused = self._ax_attribute(app, 'AXMainWindow')
        if focused is None:
            return None
        bounds = self._ax_rect(focused)
        if bounds is None:
            return None
        return (
            bounds.x1, bounds.y1, bounds.x2, bounds.y2
        ) == (outer.x1, outer.y1, outer.x2, outer.y2)

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

    @staticmethod
    def _ax_bounds_key(rect: Rect) -> tuple[int, int, int, int]:
        return rect.x1, rect.y1, rect.x2, rect.y2

    def _find_ax_window(self, owner_pid: int, outer: Rect) -> object | None:
        """在应用的 AXWindows 中按外框尺寸定位目标窗口元素。

        Args:
            owner_pid: 窗口所属进程 ID
            outer: CGWindowList 返回的窗口完整外框（含标题栏）

        Returns:
            匹配的 AX 窗口元素，找不到返回 None
        """
        target = self._ax_bounds_key(outer)
        app = AS.AXUIElementCreateApplication(owner_pid)
        for ax_window in self._ax_attribute(app, 'AXWindows') or []:
            bounds = self._ax_rect(ax_window)
            if bounds is not None and self._ax_bounds_key(bounds) == target:
                return ax_window
        return None

    @property
    def win_rect(self) -> Rect | None:
        """Use the same content viewport for screenshots and click coordinates."""
        outer = self.window_rect
        window = self.get_win()
        if outer is None or window is None:
            return None
        ax_window = self._find_ax_window(window.owner_pid, outer)
        if ax_window is not None:
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

    def _raise_game_window(self, window: MacGameWindowHandle) -> bool:
        """用 Accessibility 把目标游戏窗口提为前台应用的主窗口。

        仅激活应用（NSRunningApplication.activate）时，PlayCover 可能只把应用
        切到前台而不让游戏窗口成为焦点窗口，键盘输入会落到别的窗口；
        这里按外框尺寸找到对应 AX 窗口，置为主窗口与焦点窗口并执行 AXRaise。

        Args:
            window: 目标游戏窗口句柄

        Returns:
            是否成功对窗口执行了提起操作
        """
        outer = self.window_rect
        if outer is None:
            return False
        ax_window = self._find_ax_window(window.owner_pid, outer)
        if ax_window is None:
            return False
        AS.AXUIElementSetAttributeValue(ax_window, 'AXMain', kCFBooleanTrue)
        AS.AXUIElementSetAttributeValue(ax_window, 'AXFocused', kCFBooleanTrue)
        return AS.AXUIElementPerformAction(ax_window, 'AXRaise') == 0

    def active(self) -> bool:
        window = self.get_win()
        if window is None:
            return False
        if self.is_win_active:
            self._activate_error_logged = False
            return True
        app_activated = window.activate()
        window_raised = self._raise_game_window(window)
        if not app_activated and not window_raised:
            if not self._activate_error_logged:
                log.error(gt('无法激活 PlayCover 游戏窗口，请检查系统辅助功能权限', model='log'))
                self._activate_error_logged = True
            return False
        self._activate_error_logged = False
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
