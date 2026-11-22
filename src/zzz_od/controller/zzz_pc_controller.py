import math
import sys
import threading
import time

import pyautogui
from cv2.typing import MatLike

from one_dragon.base.controller.pc_button.keyboard_mouse_controller import (
    KeyboardMouseController,
)
from one_dragon.base.controller.pc_controller_base import PcControllerBase
from one_dragon.base.geometry.point import Point
from one_dragon.utils import cv2_utils
from zzz_od.config.game_config import GameConfig
from zzz_od.const import game_const
from zzz_od.screen_area.screen_normal_world import ScreenNormalWorldEnum


class ZPcController(PcControllerBase):

    # ZZZ 3.3.1 的桌面模式 hook(libUnityDesktopMode.dylib)因指令不匹配失效,
    # PlayCover 只能跑触屏布局:键盘按键进不了游戏,移动走虚拟摇杆、交互走屏幕按钮。
    # 桌面模式修复后把 touch_ui_enabled 置 False 回到键盘鼠标。
    TOUCH_MOVE_DIRECTIONS: dict[str, tuple[float, float]] = {
        'move_w': (0.0, -1.0),
        'move_s': (0.0, 1.0),
        'move_a': (-1.0, 0.0),
        'move_d': (1.0, 0.0),
    }
    TOUCH_KEY_ACTIONS: tuple[str, ...] = ('move_w', 'move_s', 'move_a', 'move_d', 'interact')

    # 触屏布局坐标(1920×1080 游戏空间),已按实机截图校准:
    # 摇杆中心在左下、交互按钮在右下按钮簇。
    TOUCH_JOYSTICK_CENTER: Point = Point(403, 780)
    TOUCH_JOYSTICK_RADIUS: float = 105.0
    TOUCH_BUTTON_POS: dict[str, Point] = {
        'interact': Point(1577, 803),
        'dodge': Point(1716, 907),
        'special_attack': Point(1424, 907),
        'ultimate': Point(1716, 518),
        'switch_next': Point(1716, 724),
    }
    TOUCH_NORMAL_ATTACK: Point = Point(1570, 805)
    TOUCH_MOVE_TAP_SECONDS: float = 0.3

    def __init__(
            self,
            game_config: GameConfig,
            screenshot_method: str,
            standard_width: int = 1920,
            standard_height: int = 1080,
            keyboard_mouse_controller: KeyboardMouseController | None = None,
    ):
        PcControllerBase.__init__(self,
                                  screenshot_method=screenshot_method,
                                  standard_width=standard_width,
                                  standard_height=standard_height,
                                  keyboard_mouse_controller=keyboard_mouse_controller)

        self.game_config: GameConfig = game_config
        self.action_keys = self.game_config.get_action_keys()

        self.is_moving: bool = False  # 是否正在移动
        self.touch_ui_enabled: bool = sys.platform == 'darwin'
        self._touch_move_actions: set[str] = set()
        self._touch_vec: Point = Point(0, 0)
        self._touch_owner: str | None = None
        self._touch_lock: threading.RLock = threading.RLock()
        self._touch_generation: int = 0
        self._touch_move_tokens: dict[str, object] = {}

    def sync_game_config(self, game_config: GameConfig) -> None:
        """切换实例后同步控制器持有的账号级配置"""
        self.game_config = game_config

        self.enable_foreground_mode()

    def init_before_context_run(self) -> bool:
        """运行前启用前台键鼠模式。"""
        self.enable_foreground_mode()
        return PcControllerBase.init_before_context_run(self)

    def fill_uid_black(self, screen: MatLike) -> MatLike:
        """
        遮挡UID 由子类实现
        """
        rect = ScreenNormalWorldEnum.UID.value.rect

        return cv2_utils.mark_area_as_color(
            screen,
            pos=[rect.x1, rect.y1, rect.width, rect.height],
            color=game_const.YOLO_DEFAULT_COLOR,
            new_image=True
        )

    def enable_keyboard(self):
        PcControllerBase.enable_keyboard(self)
        self.action_keys = self.game_config.get_action_keys()

    def btn_tap(self, key: str) -> None:
        """点按键:触屏模式下移动/交互键改走摇杆与屏幕按钮。"""
        if self._route_touch_key(key, 'tap', None):
            return
        PcControllerBase.btn_tap(self, key)

    def btn_press(self, key: str, press_time: float | None = None) -> None:
        """按住键:触屏模式下移动键改为按住摇杆偏转。"""
        if self._route_touch_key(key, 'press', press_time):
            return
        PcControllerBase.btn_press(self, key, press_time)

    def btn_release(self, key: str) -> None:
        """释放键:触屏模式下移动键松开摇杆回中。"""
        if self._route_touch_key(key, 'release', None):
            return
        PcControllerBase.btn_release(self, key)

    def _touch_action_for_key(self, key: str) -> str | None:
        """把配置键名反查回动作名(仅触屏接管的动作)。"""
        for action in self.TOUCH_KEY_ACTIONS:
            if self.action_keys.get(action) == key:
                return action
        return None

    def _route_touch_key(self, key: str, action: str, press_time: float | None) -> bool:
        """触屏模式下把移动/交互键路由到摇杆与屏幕按钮。

        Args:
            key: 框架键名(如 'w'/'f',取自 game_config)
            action: 'tap' / 'press' / 'release'
            press_time: press 时的定时保持时长(秒)

        Returns:
            是否已被触屏路由处理;未处理返回 False 走原键盘路径
        """
        if not self.touch_ui_enabled:
            return False
        touch_action = self._touch_action_for_key(key)
        if touch_action is None:
            return False
        if touch_action in self.TOUCH_MOVE_DIRECTIONS:
            self._touch_move_action(touch_action, action, press_time)
            return True
        pos = self.TOUCH_BUTTON_POS.get(touch_action)
        if pos is not None:
            if action == 'release':
                # 屏幕按钮是瞬时触发,没有按住态;release 只吞掉不重复触发
                return True
            # 屏幕按钮按 tap 处理;press/release 语义不区分(按钮为瞬时触发)
            hold = press_time if press_time and press_time > 0 else 0.1
            with self._touch_lock:
                if not self._touch_held:
                    self.click(pos, press_time=hold, pc_alt=False)
            return True
        return False

    def _touch_move_action(self, action: str, action_kind: str, press_time: float | None) -> None:
        """执行摇杆动作，其他动作占用触点时忽略。"""
        with self._touch_lock:
            if action_kind == 'release':
                if self._touch_owner == 'move':
                    self._touch_move_tokens.pop(action, None)
                    self._touch_move_actions.discard(action)
                    self._apply_touch_move()
                return
            if self._touch_owner not in (None, 'move') or (self._touch_held and self._touch_owner is None):
                return
            if action_kind == 'tap':
                self._touch_move_tap(action)
                return
            token = object()
            self._touch_move_tokens[action] = token
            self._touch_move_actions.add(action)
            self._apply_touch_move()
            generation = self._touch_generation
        if press_time is not None:
            try:
                time.sleep(press_time)
            finally:
                with self._touch_lock:
                    if (self._touch_owner == 'move' and self._touch_generation == generation
                            and self._touch_move_tokens.get(action) is token):
                        self._touch_move_tokens.pop(action, None)
                        self._touch_move_actions.discard(action)
                        self._apply_touch_move()

    def _touch_move_vector(self) -> Point:
        """把按住的移动动作合成摇杆偏转量(相对摇杆中心的游戏坐标偏移)。"""
        x = (1.0 if 'move_d' in self._touch_move_actions else 0.0) - (
            1.0 if 'move_a' in self._touch_move_actions else 0.0)
        y = (1.0 if 'move_s' in self._touch_move_actions else 0.0) - (
            1.0 if 'move_w' in self._touch_move_actions else 0.0)
        if x == 0.0 and y == 0.0:
            return Point(0, 0)
        # 斜向归一化到满偏转,避免合成向量超出摇杆半径
        length = math.hypot(x, y)
        scale = self.TOUCH_JOYSTICK_RADIUS / length
        return Point(x * scale, y * scale)

    def _touch_screen_delta(self, dx: float, dy: float) -> tuple[float, float]:
        """把游戏坐标增量换算成屏幕像素增量(窗口缩放)。"""
        rect = self.game_win.win_rect
        if rect is None or rect.width <= 0 or rect.height <= 0:
            return dx, dy
        return (
            dx * rect.width / self.standard_width,
            dy * rect.height / self.standard_height,
        )

    def _apply_touch_move(self) -> None:
        """按当前按住的移动键刷新摇杆偏转;全部松开时回中并抬起触点。"""
        target = self._touch_move_vector()
        if target.x == self._touch_vec.x and target.y == self._touch_vec.y:
            return
        if not self._touch_held:
            if target.x == 0 and target.y == 0:
                return
            if not self.touch_down(self.TOUCH_JOYSTICK_CENTER):
                self._touch_move_actions.clear()
                self._touch_move_tokens.clear()
                self._touch_vec = Point(0, 0)
                return
            self._touch_owner = 'move'
            self._touch_generation += 1
        dx, dy = self._touch_screen_delta(
            target.x - self._touch_vec.x, target.y - self._touch_vec.y)
        self.touch_move_relative(dx, dy)
        self._touch_vec = target
        if target.x == 0 and target.y == 0:
            self._touch_owner = None
            self.touch_up()

    def _touch_move_tap(self, action: str) -> None:
        """短促摇杆偏转:按下→偏向该方向→保持→抬起。"""
        if self._touch_held:
            # 已有按住的移动(如 w 长按中),tap 会破坏按住状态,直接忽略
            return
        dir_x, dir_y = self.TOUCH_MOVE_DIRECTIONS[action]
        if not self.touch_down(self.TOUCH_JOYSTICK_CENTER):
            return
        dx, dy = self._touch_screen_delta(
            dir_x * self.TOUCH_JOYSTICK_RADIUS * 0.9,
            dir_y * self.TOUCH_JOYSTICK_RADIUS * 0.9)
        try:
            self.touch_move_relative(dx, dy)
            time.sleep(self.TOUCH_MOVE_TAP_SECONDS)
        finally:
            self.touch_up()

    def _action_btn(self, key: str, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """通用按键动作：按下/释放/点按"""
        if press:
            self.btn_press(key, press_time)
        elif release:
            self.btn_release(key)
        else:
            self.btn_tap(key)

    def _touch_btn_or_action_btn(
            self, touch_action: str, key: str,
            press: bool, press_time: float | None, release: bool) -> None:
        """触屏模式下把战斗按钮动作路由到屏幕坐标点击;否则走键盘键。"""
        if self.touch_ui_enabled:
            # 屏幕按钮为瞬时触发,只处理点击;press/release 不区分,
            # 但摇杆按住(_touch_held)或 release 语义时不触发
            with self._touch_lock:
                if not self._touch_held and not release:
                    self.click(
                        self.TOUCH_BUTTON_POS[touch_action],
                        press_time=press_time or 0.1, pc_alt=False)
            return
        self._action_btn(key, press, press_time, release)

    def dodge(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """闪避"""
        self._touch_btn_or_action_btn(
            'dodge', self.action_keys['dodge'], press, press_time, release)

    def switch_next(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """切换角色-下一个"""
        self._touch_btn_or_action_btn(
            'switch_next', self.action_keys['switch_next'], press, press_time, release)

    def switch_prev(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """切换角色-上一个"""
        self._action_btn(self.action_keys['switch_prev'], press, press_time, release)

    def switch_backup(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """切换后援"""
        self._action_btn(self.action_keys['switch_backup'], press, press_time, release)

    def _touch_attack(self, owner: str, pos: Point, press: bool,
                      press_time: float | None, release: bool) -> None:
        """按住或释放指定攻击，忽略其他动作占用的触点。"""
        with self._touch_lock:
            if press:
                if self._touch_held or not self.touch_down(pos):
                    return
                self._touch_owner = owner
                self._touch_generation += 1
                generation = self._touch_generation
            elif release:
                if self._touch_owner == owner:
                    self._touch_owner = None
                    self.touch_up()
                return
            else:
                if not self._touch_held:
                    self.click(pos, press_time=0.1, pc_alt=False)
                return
        if press_time is not None:
            try:
                time.sleep(press_time)
            finally:
                with self._touch_lock:
                    if self._touch_owner == owner and self._touch_generation == generation:
                        self._touch_owner = None
                        self.touch_up()

    def touch_up(self) -> None:
        """抬起触点并清除对应动作状态。"""
        with self._touch_lock:
            self._touch_owner = None
            self._touch_move_actions.clear()
            self._touch_move_tokens.clear()
            self._touch_vec = Point(0, 0)
            self._touch_generation += 1
            PcControllerBase.touch_up(self)

    def normal_attack(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """普通攻击"""
        if self.touch_ui_enabled:
            self._touch_attack('normal_attack', self.TOUCH_NORMAL_ATTACK, press, press_time, release)
            return
        self._action_btn(self.action_keys['normal_attack'], press, press_time, release)

    def special_attack(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """特殊攻击"""
        if self.touch_ui_enabled:
            self._touch_attack('special_attack', self.TOUCH_BUTTON_POS['special_attack'], press, press_time, release)
            return
        self._action_btn(self.action_keys['special_attack'], press, press_time, release)

    def ultimate(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """终结技"""
        self._touch_btn_or_action_btn(
            'ultimate', self.action_keys['ultimate'], press, press_time, release)

    def chain_left(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """连携技-左"""
        self._action_btn(self.action_keys['chain_left'], press, press_time, release)

    def chain_right(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """连携技-右"""
        self._action_btn(self.action_keys['chain_right'], press, press_time, release)

    def move_w(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向前移动"""
        self._action_btn(self.action_keys['move_w'], press, press_time, release)

    def move_s(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向后移动"""
        self._action_btn(self.action_keys['move_s'], press, press_time, release)

    def move_a(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向左移动"""
        self._action_btn(self.action_keys['move_a'], press, press_time, release)

    def move_d(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向右移动"""
        self._action_btn(self.action_keys['move_d'], press, press_time, release)

    def interact(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """交互"""
        self._action_btn(self.action_keys['interact'], press, press_time, release)

    def lock(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """锁定敌人"""
        self._action_btn(self.action_keys['lock'], press, press_time, release)

    def chain_cancel(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """取消连携"""
        self._action_btn(self.action_keys['chain_cancel'], press, press_time, release)

    def start_moving_forward(self) -> None:
        """
        开始向前移动
        """
        if self.is_moving:
            return
        self.is_moving = True
        self.move_w(press=True)

    def stop_moving_forward(self) -> None:
        """
        停止向前移动
        """
        self.is_moving = False
        self.move_w(release=True)

    def turn_by_distance(self, d: float):
        """
        横向转向 按距离转

        Args:
            d: 正数往右转 负数往左转
        """
        if self.touch_ui_enabled:
            # 触屏模式下通过触摸滑动旋转镜头
            # d > 0 向右转 -> 视角向右，触点向左划
            # d < 0 向左转 -> 视角向左，触点向右划
            max_drag = 300.0
            drag_dx = max(-max_drag, min(max_drag, float(d)))
            center_x, center_y = 1400, 500
            start = Point(center_x, center_y)
            end = Point(int(center_x - drag_dx), center_y)
            with self._touch_lock:
                if not self._touch_held:
                    self.touch_drag_hold(start, end, move_time=0.15, hold_time=0.05)
            return
        self.move_mouse_relative(d, 0)

    def turn_by_angle_diff(self, angle_diff: float) -> None:
        """
        按照给定角度偏移进行转向

        Args:
            angle_diff: 角度偏移 逆时针为正

        Returns:
            None
        """
        self.turn_by_distance(self.game_config.turn_dx * angle_diff)

    def turn_vertical_by_distance(self, d: float):
        """
        纵向转向 按距离转

        Args:
            d: 正数往下转 负数往上转
        """
        if self.touch_ui_enabled:
            max_drag = 200.0
            drag_dy = max(-max_drag, min(max_drag, float(d)))
            center_x, center_y = 1400, 500
            start = Point(center_x, center_y)
            end = Point(center_x, int(center_y - drag_dy))
            with self._touch_lock:
                if not self._touch_held:
                    self.touch_drag_hold(start, end, move_time=0.15, hold_time=0.05)
            return
        self.move_mouse_relative(0, d)

    def move_mouse_relative(self, dx: float, dy: float):
        """
        相对移动鼠标

        Args:
            dx: 横向移动距离，正数向右
            dy: 纵向移动距离，正数向下
        """
        if dx == 0 and dy == 0:
            return
        if sys.platform == 'darwin':
            if not self.game_win.is_win_active:
                self.game_win.active()
                time.sleep(self.MAC_ACTIVE_SETTLE)
            self._get_mac_virtual_hid_mouse().move_relative(round(dx), round(dy))
            return
        pyautogui.moveRel(int(dx), int(dy), duration=0)
