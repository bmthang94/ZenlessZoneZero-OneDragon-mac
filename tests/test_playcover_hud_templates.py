import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from one_dragon.base.screen.screen_loader import ScreenContext
from one_dragon.base.screen.template_loader import TemplateLoader
from zzz_od.controller.zzz_pc_controller import ZPcController


def test_playcover_hud_screen_areas():
    print("=== 1. VERIFY SCREEN INFO REGISTRATION (battle.yml & _od_merged.yml) ===")
    loader = ScreenContext()
    # Load from merged (runtime path)
    loader.reload(from_separated_files=False)
    battle_merged = loader.get_screen('战斗画面')

    # Check PlayCover areas registered in merged cache
    area_names = {a.area_name: a for a in battle_merged.area_list}
    assert '按键-特殊攻击-PlayCover' in area_names, "Missing 按键-特殊攻击-PlayCover in merged screen_info"
    assert '按键-切换角色-PlayCover' in area_names, "Missing 按键-切换角色-PlayCover in merged screen_info"
    assert '按键-终结技-PlayCover' in area_names, "Missing 按键-终结技-PlayCover in merged screen_info"

    # Verify template IDs
    assert area_names['按键-特殊攻击-PlayCover'].template_id == 'btn_special_attack_playcover'
    assert area_names['按键-切换角色-PlayCover'].template_id == 'btn_switch_next_playcover'
    assert area_names['按键-终结技-PlayCover'].template_id == 'btn_ultimate_playcover'

    # Verify bounding boxes are left open ([0, 0, 0, 0]) pending full 1080p frame
    for name in ['按键-特殊攻击-PlayCover', '按键-切换角色-PlayCover', '按键-终结技-PlayCover']:
        rect = area_names[name].pc_rect
        assert (rect.x1, rect.y1, rect.x2, rect.y2) == (0, 0, 0, 0), f"Expected open rect (0,0,0,0) for {name}, got {rect}"
        print(f"  [OK] {name} -> template_id={area_names[name].template_id}, rect=[0, 0, 0, 0] (open)")

    # Verify PC areas remain untouched
    pc_special = area_names.get('按键-特殊攻击')
    assert pc_special is not None
    assert (pc_special.pc_rect.x1, pc_special.pc_rect.y1, pc_special.pc_rect.x2, pc_special.pc_rect.y2) == (1620, 917, 1720, 1017)
    print("  [OK] PC area 按键-特殊攻击 rect preserved intact: [1620, 917, 1720, 1017]")

    pc_ultimate = area_names.get('按键-终结技')
    assert pc_ultimate is not None
    assert (pc_ultimate.pc_rect.x1, pc_ultimate.pc_rect.y1, pc_ultimate.pc_rect.x2, pc_ultimate.pc_rect.y2) == (1728, 778, 1826, 876)
    print("  [OK] PC area 按键-终结技 rect preserved intact: [1728, 778, 1826, 876]")

    pc_switch = area_names.get('按键-切换角色')
    assert pc_switch is not None
    assert (pc_switch.pc_rect.x1, pc_switch.pc_rect.y1, pc_switch.pc_rect.x2, pc_switch.pc_rect.y2) == (1731, 920, 1827, 1016)
    print("  [OK] PC area 按键-切换角色 rect preserved intact: [1731, 920, 1827, 1016]")


def test_playcover_templates_loading():
    print("\n=== 2. VERIFY TEMPLATE LOADER & MATCHER ===")
    tl = TemplateLoader()

    templates = [
        'btn_special_attack_playcover',
        'btn_switch_next_playcover',
        'btn_ultimate_playcover'
    ]

    for tid in templates:
        tpl = tl.load_template('battle', tid)
        assert tpl is not None, f"Template {tid} could not be loaded"
        assert tpl.raw is not None, f"Template {tid} raw image missing"
        assert tpl.mask is not None, f"Template {tid} mask image missing"
        print(f"  [OK] {tid} -> raw shape {tpl.raw.shape}, mask shape {tpl.mask.shape}")


def test_touch_button_positions():
    print("\n=== 3. VERIFY TOUCH COORDINATES IN CONTROLLER ===")
    touch_pos = ZPcController.TOUCH_BUTTON_POS
    assert touch_pos['ultimate'].tuple() == (1716, 518), f"Expected ultimate Point(1716, 518), got {touch_pos['ultimate']}"
    assert touch_pos['switch_next'].tuple() == (1716, 724), f"Expected switch_next Point(1716, 724), got {touch_pos['switch_next']}"
    assert touch_pos['dodge'].tuple() == (1716, 907), f"Expected dodge Point(1716, 907), got {touch_pos['dodge']}"
    assert touch_pos['special_attack'].tuple() == (1424, 907), f"Expected special_attack Point(1424, 907), got {touch_pos['special_attack']}"
    assert ZPcController.TOUCH_NORMAL_ATTACK.tuple() == (1570, 805), f"Expected normal_attack Point(1570, 805), got {ZPcController.TOUCH_NORMAL_ATTACK}"
    print(f"  [OK] ultimate position: {touch_pos['ultimate']} (Calibrated to vertical axis x=1716)")
    print(f"  [OK] switch_next position: {touch_pos['switch_next']}")
    print(f"  [OK] dodge position: {touch_pos['dodge']}")
    print(f"  [OK] special_attack position: {touch_pos['special_attack']}")
    print(f"  [OK] normal_attack position: {ZPcController.TOUCH_NORMAL_ATTACK}")


if __name__ == '__main__':
    test_playcover_hud_screen_areas()
    test_playcover_templates_loading()
    test_touch_button_positions()
    print("\n>>> ALL PLAYCOVER HUD TEMPLATE & SCREEN AREA TESTS PASSED! <<<")
