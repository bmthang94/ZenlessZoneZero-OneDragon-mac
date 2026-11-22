from collections.abc import Callable

from one_dragon.base.screen.screen_area import ScreenArea
from one_dragon.base.screen.screen_loader import ScreenContext


class ZScreenContext(ScreenContext):
    def __init__(self, uses_playcover_touch_ui: Callable[[], bool]) -> None:
        super().__init__()
        self._uses_playcover_touch_ui: Callable[[], bool] = uses_playcover_touch_ui

    def get_area(self, screen_name: str, area_name: str) -> ScreenArea:
        if (screen_name == '战斗画面' and area_name == '按键-普通攻击'
                and self._uses_playcover_touch_ui()):
            area_name = '按键-普通攻击-PlayCover'
        return super().get_area(screen_name, area_name)
