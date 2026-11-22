import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from one_dragon.base.conditional_operation.state_recorder import StateRecord
from zzz_od.auto_battle.auto_battle_context import AutoBattleContext
from zzz_od.context.zzz_context import ZContext
from zzz_od.controller.zzz_pc_controller import ZPcController


def test_remielle_rotation_offline():
    ctx = ZContext()
    battle_ctx = AutoBattleContext(ctx)

    # Initialize auto_battle with the new merged preset
    preset_name = "Remielle M2 - Phoenix - Velina"
    battle_ctx.init_auto_op(sub_dir="auto_battle", op_name=preset_name)
    op = battle_ctx.auto_op
    assert op is not None, "Failed to load AutoBattleOperator"
    state_service = op.state_record_service

    print("=== 1. VERIFY ZERO TURN / ZERO LOCK / ZERO SPAM FLAGS ===")
    assert op.auto_turn_interval == 0, f"Expected auto_turn_interval 0, got {op.auto_turn_interval}"
    assert op.auto_lock_interval == 0, f"Expected auto_lock_interval 0, got {op.auto_lock_interval}"
    assert getattr(op, "fallback_attack_enabled", True) is False, "Expected fallback_attack_enabled to be False"
    print(f"auto_turn_interval: {op.auto_turn_interval} (OK)")
    print(f"auto_lock_interval: {op.auto_lock_interval} (OK)")
    print(f"fallback_attack_enabled: {op.fallback_attack_enabled} (OK)")

    now = time.time()

    def reset_states():
        battle_ctx.clear_all_states()

    def set_state(name: str, value: float = 1):
        state_service.update_state(StateRecord(name, now, value=value))

    # --- Scenario 1: Opener Step 1 (Remielle on field) ---
    print("\n--- 1. Opener Step 1: Remielle on field ---")
    reset_states()
    set_state("前台-蕾米埃尔")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None, "Opener Step 1 should match"
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Opener Step 1" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    print(f"          Ops: {ops[:6]}... (total {len(ops)})")
    # Verify hold basic 2s (4 x 0.5s down), hold special 1s (2 x 0.5s down), double next swap
    assert ops.count("按键-普通攻击按下") == 4
    assert ops.count("按键-特殊攻击按下") == 2
    assert ops.count("按键-切换角色-下一个") == 2

    # --- Scenario 2: Opener Step 2 (Velina on field) ---
    print("\n--- 2. Opener Step 2: Velina on field (Single tap EX -> Hold EX 1.5s -> Quick Assist) ---")
    reset_states()
    set_state("前台-维琳娜")
    set_state("自定义-开场-维琳娜")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None, "Opener Step 2 should match"
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Opener Step 2" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    print(f"          Ops: {ops}")
    # Verify: Single tap EX (tap count == 1, NOT 2), hold EX 1.5s (3 x 0.5s down)
    tap_ex_count = ops.count("按键-特殊攻击")
    hold_ex_count = ops.count("按键-特殊攻击按下")
    assert tap_ex_count == 1, f"Expected 1 tap EX, got {tap_ex_count}"
    assert hold_ex_count == 3, f"Expected 3 down steps (1.5s), got {hold_ex_count}"
    assert "设置状态 自定义-开场-维琳娜EX完成" in ops
    assert "按键-快速支援" in ops

    # 2b. Bounded retry Quick Assist on prompt if Velina remains on field (preserves Phase Flow, NO double next)
    print("\n--- 2b. Opener Step 2b: Bounded retry Quick Assist on prompt (NO double next swap) ---")
    set_state("自定义-开场-维琳娜EX完成")
    set_state("按键可用-快速支援")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Opener Step 2b" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert "按键-快速支援" in ops
    assert ops.count("按键-切换角色-下一个") == 0, "Must NOT use double next swap through Remielle in Opener"

    # 2c. Bounded wait while awaiting Quick Assist transition without faking completed
    print("\n--- 2c. Opener Step 2c: Bounded wait awaiting Quick Assist transition ---")
    reset_states()
    set_state("前台-维琳娜")
    set_state("自定义-开场-维琳娜")
    set_state("自定义-开场-维琳娜EX完成")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Opener Step 2c" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert "设置状态 自定义-开场连招完成" not in ops, "Must NOT fake completed while awaiting"

    # 2d. Opener Step 3: Phoenix Confirmed on Field -> Formally Complete Opener
    print("\n--- 2d. Opener Step 3: Phoenix Confirmed on Field -> Complete Opener ---")
    reset_states()
    set_state("前台-菲欧妮")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Opener Step 3" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert "设置状态 自定义-开场连招完成" in ops

    # Mark Opener Complete for subsequent tests
    reset_states()
    set_state("自定义-开场连招完成")

    # --- Scenario 3: Opener Guard ---
    print("\n--- 3. Opener Guard: Remielle on field after opener complete ---")
    set_state("前台-蕾米埃尔")
    set_state("蕾米埃尔-虚曜", value=3)
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Opener" not in match_result.expr_display
    assert "Remielle Discharge 3 Voidflare" in match_result.expr_display

    # --- Scenario 4: Phoenix Purifying Flame Guarded with Burn OR Windswept (Real Target State) ---
    print("\n--- 4. Phoenix Purifying Flame: Pyre >= 90 & (Burn OR Windswept real state) ---")
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("前台-菲欧妮")
    set_state("菲欧妮-燔焰", value=95)

    # 4a: Without Burn and without Windswept -> Purifying Flame MUST NOT match! Falls back to Basic x4
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    assert "Phoenix Purifying Flame" not in match_result.expr_display
    assert "Phoenix Basic Attack x4" in match_result.expr_display
    print("  [OK] Guard verified: Purifying Flame blocked when Burn/Windswept absent")

    # 4b: Custom State alone (e.g. 自定义-菲欧妮-灼烧) does NOT trigger Main Loop Purifying Flame (waits for real target state)
    set_state("自定义-菲欧妮-灼烧")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    assert "Phoenix Purifying Flame" not in match_result.expr_display
    assert "Phoenix Basic Attack x4" in match_result.expr_display
    print("  [OK] Guard verified: Custom state alone does not fake real OCR anomaly")

    # 4c: With Genuine Target Anomaly: Burn ONLY -> Matches Purifying Flame!
    set_state("目标-异常-灼烧")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH (Burn Only)] {match_result.expr_display}")
    assert "Phoenix Purifying Flame" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    # Verify: 3 x 0.5s down = 1.5s
    down_count = ops.count("按键-普通攻击按下")
    assert down_count == 3, f"Expected 3 down steps (1.5s), got {down_count}"
    assert "按键-普通攻击松开" in ops
    assert "按键-切换角色-下一个" in ops

    # 4d: With Genuine Target Anomaly: Windswept ONLY -> Matches Purifying Flame! (Burn OR Windswept)
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("前台-菲欧妮")
    set_state("菲欧妮-燔焰", value=95)
    set_state("目标-异常-风蚀")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH (Windswept Only)] {match_result.expr_display}")
    assert "Phoenix Purifying Flame" in match_result.expr_display

    # --- Scenario 5: Phoenix Transition to Remielle via double Next Swap ---
    print("\n--- 5. Phoenix Transition to Remielle (Touch Transport: double Next Swap) ---")
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("前台-菲欧妮")
    set_state("蕾米埃尔-虚曜", value=3)
    set_state("后台-蕾米埃尔")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Phoenix Transition to Remielle" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    print(f"          Ops: {ops}")
    # Verify double Next Swap touch transport (no switch_prev PC fallback)
    assert ops.count("按键-切换角色-下一个") == 2

    # --- Scenario 6: Phoenix EX Special sequence (No repeat 6 / 10 spam) ---
    print("\n--- 6. Phoenix EX Special: Clean 3-step sequence (No repeat 6/10 spam) ---")
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("前台-菲欧妮")
    set_state("菲欧妮-特殊技可用")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Phoenix EX Special Chain" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    print(f"          Ops: {ops}")
    assert ops.count("按键-特殊攻击") == 3
    for node in match_result.op_list:
        assert getattr(node, "repeat", 1) == 1, "Expected single operation, no repeat loop"

    # --- Scenario 7: Absent readiness verification ---
    print("\n--- 7. Absent Readiness Test: Phoenix without readiness / energy falls back to Basic x4 ---")
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("前台-菲欧妮")
    # No energy, no special available, no pyre
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "Phoenix Basic Attack x4" in match_result.expr_display

    # --- Scenario 8: Chain attack selection with Remielle 3 Voidflare ---
    print("\n--- 8. Chain Attack with Remielle 3 Voidflare: Strictly avoids Remielle, no unconditional left ---")
    trigger_scene = op.trigger_2_scene.get("按键可用-连携技")
    assert trigger_scene is not None, "Trigger 按键可用-连携技 not found"
    reset_states()
    set_state("蕾米埃尔-虚曜", value=3)
    set_state("连携技-1-维琳娜")
    match_result = trigger_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH] {match_result.expr_display}")
    assert "连携技-1-维琳娜" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert "按键-连携技-左" in ops
    assert "设置状态 自定义-失衡时间" not in ops, "Must NOT mark chained/stunned merely on emitting key"

    # Test that Remielle is NOT selected when Remielle holds 3 Voidflare
    reset_states()
    set_state("蕾米埃尔-虚曜", value=3)
    set_state("连携技-1-蕾米埃尔")
    match_result = trigger_scene.match_execution(now)
    if match_result is not None:
        print("  [DEBUG MATCH RESULT]", match_result.expr_display)
    assert match_result is None, "Should NOT match Remielle when Remielle holds 3 Voidflare"
    print("  [OK] Remielle successfully excluded from Chain Attack when holding 3 Voidflare")

    # --- Scenario 9: Stun Window Sequence ---
    print("\n--- 9. Stun Window Sequence: Phoenix Ult/Hold Basic -> Remielle Entry/Ult/Burst ---")
    # 9a: Ultimate available -> Phoenix Stun Ultimate
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("自定义-失衡时间")  # 0s into Stun
    set_state("前台-菲欧妮")
    set_state("菲欧妮-终结技可用")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH Phase 1 (Ult Ready)] {match_result.expr_display}")
    assert "Phoenix Stun Ultimate" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert "按键-终结技" in ops
    assert ops.count("按键-切换角色-下一个") == 2

    # 9b: Stun Fallback: Ultimate NOT available, but Pyre >= 90 -> Matches Purifying Flame without requiring anomaly!
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("自定义-失衡时间")
    set_state("前台-菲欧妮")
    set_state("菲欧妮-燔焰", value=95)
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH Phase 1 (Stun Fallback Pyre >= 90)] {match_result.expr_display}")
    assert "Phoenix Stun Purifying Flame" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert ops.count("按键-普通攻击按下") == 3  # 1.5s hold basic
    assert ops.count("按键-切换角色-下一个") == 2  # switch to Remielle

    # 9c: Stun Fallback: Ultimate NOT available and Pyre < 90 -> Direct Transition to Remielle
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("自定义-失衡时间")
    set_state("前台-菲欧妮")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH Phase 1 (Direct Transition)] {match_result.expr_display}")
    assert "Phoenix Stun Transition to Remielle" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert ops.count("按键-切换角色-下一个") == 2

    # 9d: Stun Phase 2 (Remielle on field during Stun)
    reset_states()
    set_state("自定义-开场连招完成")
    set_state("自定义-失衡时间")
    set_state("前台-蕾米埃尔")
    set_state("蕾米埃尔-终结技可用")
    match_result = op.normal_scene.match_execution(now)
    assert match_result is not None
    print(f"  [MATCH Phase 2] {match_result.expr_display}")
    assert "Remielle Stun Ultimate" in match_result.expr_display
    ops = [node.op_name for node in match_result.op_list]
    assert "按键-终结技" in ops
    assert ops.count("按键-普通攻击按下") == 4  # 2s hold basic
    assert ops.count("按键-特殊攻击按下") == 2  # 1s hold special
    assert "按键-切换角色-下一个" in ops

    print("\n>>> ALL SCENE MATCH VERIFICATION SCENARIOS PASSED SUCCESSFULLY! <<<")


def test_controller_transport_playcover():
    """
    Verify action transport on PlayCover controller.
    Distinguish between actions with calibrated touch transport and actions that fallback to PC keyboard.
    """
    print("\n=== 2. VERIFY CONTROLLER TRANSPORT ON PLAYCOVER ===")
    game_config = MagicMock()
    game_config.touch_ui_enabled = True

    controller = ZPcController(game_config=game_config, screenshot_method="mock")
    controller.touch_down = MagicMock(return_value=True)
    controller.touch_up = MagicMock()
    controller.click = MagicMock()
    controller._action_btn = MagicMock()

    # 1. Test Touch Transport Actions
    # Dodge
    controller.dodge()
    call_args = controller.click.call_args
    assert call_args[0][0].tuple() == (1716, 907), f"Expected (1716, 907), got {call_args[0][0].tuple()}"
    print("  [TOUCH] dodge -> Point(1716, 907) OK")

    # Switch Next
    controller.click.reset_mock()
    controller.switch_next()
    call_args = controller.click.call_args
    assert call_args[0][0].tuple() == (1716, 724), f"Expected (1716, 724), got {call_args[0][0].tuple()}"
    print("  [TOUCH] switch_next -> Point(1716, 724) OK")

    # Ultimate
    controller.click.reset_mock()
    controller.ultimate()
    call_args = controller.click.call_args
    assert call_args[0][0].tuple() == (1716, 518), f"Expected (1716, 518), got {call_args[0][0].tuple()}"
    print("  [TOUCH] ultimate -> Point(1716, 518) OK (Calibrated coordinate)")

    # Special Attack
    controller.click.reset_mock()
    controller.special_attack()
    call_args = controller.click.call_args
    assert call_args[0][0].tuple() == (1424, 907), f"Expected (1424, 907), got {call_args[0][0].tuple()}"
    print("  [TOUCH] special_attack -> Point(1424, 907) OK")

    # Normal Attack
    controller.click.reset_mock()
    controller.normal_attack()
    call_args = controller.click.call_args
    assert call_args[0][0].tuple() == (1570, 805), f"Expected (1570, 805), got {call_args[0][0].tuple()}"
    print("  [TOUCH] normal_attack -> Point(1570, 805) OK")

    # 2. Test PC Keyboard Fallback Actions (Actions lacking touch mapping)
    print("\n--- Identifying PC Keyboard Fallback Actions (No touch coordinates mapped) ---")

    # switch_prev
    controller._action_btn.reset_mock()
    controller.switch_prev()
    assert controller._action_btn.called, "switch_prev should call _action_btn"
    print("  [PC FALLBACK] switch_prev -> calls _action_btn(keyboard) (No mobile touch button)")

    # chain_left
    controller._action_btn.reset_mock()
    controller.chain_left()
    assert controller._action_btn.called, "chain_left should call _action_btn"
    print("  [PC FALLBACK] chain_left -> calls _action_btn(keyboard) (Touch card position uncalibrated)")

    # chain_right
    controller._action_btn.reset_mock()
    controller.chain_right()
    assert controller._action_btn.called, "chain_right should call _action_btn"
    print("  [PC FALLBACK] chain_right -> calls _action_btn(keyboard) (Touch card position uncalibrated)")

    # switch_backup
    controller._action_btn.reset_mock()
    controller.switch_backup()
    assert controller._action_btn.called, "switch_backup should call _action_btn"
    print("  [PC FALLBACK] switch_backup -> calls _action_btn(keyboard) (Quick Assist button on mobile HUD is switch_next)")

    print("\n>>> CONTROLLER TRANSPORT VERIFICATION PASSED SUCCESSFULLY! <<<")


if __name__ == '__main__':
    test_remielle_rotation_offline()
    test_controller_transport_playcover()
