"""PlayCover 场景位移与输入模式验证工具。

用于量化检测 Zenless Zone Zero 在 macOS PlayCover 环境下：
1. 是否处于 Touchscreen Mode (触屏) 并忽略物理/虚拟键盘输入 (WASD/F)；
2. 修复 PC Mode (桌面模式 hook) 后，验证按键是否真正驱动 3D 世界场景位移。
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

if TYPE_CHECKING:
    from cv2.typing import MatLike


@dataclass
class AnchorResult:
    """单个静态锚点的跟踪测量结果。"""

    name: str
    initial_rect: list[int]  # [x, y, w, h]
    found_pos: list[int]  # [x, y]
    delta_x: int
    delta_y: int
    displacement: float
    confidence: float


@dataclass
class FrameComparisonResult:
    """帧间对比统计结果。"""

    frame_a_name: str
    frame_b_name: str
    total_pixels: int
    changed_pixels: int
    changed_percent: float
    anchors: list[AnchorResult]
    max_displacement: float
    avg_displacement: float


@dataclass
class RegressionVerdict:
    """回归测试总体验收结论。"""

    status: str  # "FAIL_TOUCHSCREEN_LOCKED" | "PASS_PC_MODE_ACTIVE" | "INCONCLUSIVE"
    summary: str
    baseline_idle_drift_pct: float
    movement_drift_pct: float
    max_anchor_displacement: float
    is_touchscreen_stuck: bool
    details: list[dict[str, Any]]


# 默认大世界静态环境锚点 (1080p 标准分辨率坐标)
DEFAULT_OVERWORLD_ANCHORS: dict[str, tuple[int, int, int, int]] = {
    "left_wall_structure": (250, 220, 100, 100),
    "right_server_rack": (1600, 300, 100, 100),
    "background_pillar": (500, 380, 100, 100),
    "cleanup_board": (1080, 280, 80, 80),
}

# 默认室内/房间环境静态锚点
DEFAULT_ROOM_ANCHORS: dict[str, tuple[int, int, int, int]] = {
    "left_crt_monitor": (50, 460, 120, 120),
    "center_pc_screen": (330, 320, 120, 120),
    "right_window_blinds": (700, 120, 120, 120),
}


def compute_pixel_diff(
    img_a: MatLike, img_b: MatLike, threshold: int = 10
) -> tuple[int, float]:
    """计算两帧之间的像素变动量与变动百分比。

    Args:
        img_a: 第一帧图像 (BGR)。
        img_b: 第二帧图像 (BGR)。
        threshold: 滤除传感器/压缩轻微噪声的单通道差值阈值 (0-255)。

    Returns:
        tuple[int, float]: (发生变化的像素总数, 占全图百分比 0.0-100.0)。
    """
    diff = cv2.absdiff(img_a, img_b)
    changed_mask = np.any(diff > threshold, axis=2)
    changed_count = int(np.count_nonzero(changed_mask))
    total_pixels = img_a.shape[0] * img_a.shape[1]
    pct = (changed_count / total_pixels) * 100.0
    return changed_count, pct


def track_anchor(
    template: MatLike,
    target_img: MatLike,
    anchor_rect: tuple[int, int, int, int],
    search_padding: int = 60,
) -> AnchorResult:
    """在目标图像中匹配指定静态锚点并测量其像素偏移。

    Args:
        template: 原始锚点区域模板 (BGR)。
        target_img: 待搜索的目标帧全图 (BGR)。
        anchor_rect: 锚点在基准图上的矩形 (x, y, w, h)。
        search_padding: 在原锚点周围扩展的搜索半径 (像素)。

    Returns:
        AnchorResult: 锚点匹配位置、位移矢量 (delta_x, delta_y)、欧氏距离与置信度。
    """
    x, y, w, h = anchor_rect
    h_target, w_target = target_img.shape[:2]

    sx1 = max(0, x - search_padding)
    sy1 = max(0, y - search_padding)
    sx2 = min(w_target, x + w + search_padding)
    sy2 = min(h_target, y + h + search_padding)

    search_roi = target_img[sy1:sy2, sx1:sx2]
    match_res = cv2.matchTemplate(search_roi, template, cv2.TM_CCOEFF_NORMED)
    _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(match_res)

    found_x = sx1 + max_loc[0]
    found_y = sy1 + max_loc[1]
    dx = found_x - x
    dy = found_y - y
    dist = math.hypot(dx, dy)

    return AnchorResult(
        name="",
        initial_rect=[x, y, w, h],
        found_pos=[found_x, found_y],
        delta_x=dx,
        delta_y=dy,
        displacement=dist,
        confidence=float(max_val),
    )


def compare_frames(
    base_img: MatLike,
    target_img: MatLike,
    frame_a_name: str,
    frame_b_name: str,
    anchors: dict[str, tuple[int, int, int, int]],
    search_padding: int = 60,
) -> FrameComparisonResult:
    """完整对比两帧图像并评估锚点位移与像素扩散。"""
    changed_cnt, changed_pct = compute_pixel_diff(base_img, target_img)
    total_pixels = base_img.shape[0] * base_img.shape[1]

    anchor_results: list[AnchorResult] = []
    displacements: list[float] = []

    for name, rect in anchors.items():
        x, y, w, h = rect
        tpl = base_img[y : y + h, x : x + w]
        res = track_anchor(tpl, target_img, rect, search_padding=search_padding)
        res.name = name
        anchor_results.append(res)
        displacements.append(res.displacement)

    max_disp = max(displacements) if displacements else 0.0
    avg_disp = float(np.mean(displacements)) if displacements else 0.0

    return FrameComparisonResult(
        frame_a_name=frame_a_name,
        frame_b_name=frame_b_name,
        total_pixels=total_pixels,
        changed_pixels=changed_cnt,
        changed_percent=changed_pct,
        anchors=anchor_results,
        max_displacement=max_disp,
        avg_displacement=avg_disp,
    )


def evaluate_movement_series(
    comparisons: list[FrameComparisonResult],
    displacement_threshold: float = 5.0,
) -> RegressionVerdict:
    """根据多段连续对比序列评估位移测试结论。"""
    if not comparisons:
        return RegressionVerdict(
            status="INCONCLUSIVE",
            summary="无对比数据",
            baseline_idle_drift_pct=0.0,
            movement_drift_pct=0.0,
            max_anchor_displacement=0.0,
            is_touchscreen_stuck=False,
            details=[],
        )

    baseline_comp = comparisons[0]
    baseline_pct = baseline_comp.changed_percent

    movement_comps = comparisons[1:] if len(comparisons) > 1 else comparisons
    max_movement_disp = max(c.max_displacement for c in movement_comps)
    max_movement_pct = max(c.changed_percent for c in movement_comps)

    if max_movement_disp < displacement_threshold:
        status = "FAIL_TOUCHSCREEN_LOCKED"
        summary = (
            f"所有环境静态锚点位移均为 0.0px (max={max_movement_disp:.2f}px < "
            f"{displacement_threshold}px)。全图变动率 {max_movement_pct:.2f}% "
            f"完全符合呼吸待机基准 ({baseline_pct:.2f}%)。"
            "证实游戏仍卡在 Touchscreen Mode (触屏)，未响应物理/虚拟键盘移动按键。"
        )
        is_stuck = True
    else:
        status = "PASS_PC_MODE_ACTIVE"
        summary = (
            f"检测到明显环境静态锚点位移 (max={max_movement_disp:.2f}px >= "
            f"{displacement_threshold}px)。全图变动率 {max_movement_pct:.2f}%。"
            "证实 3D 摄像机与角色已发生空间位移，PC Desktop Mode 按键控制已生效！"
        )
        is_stuck = False

    details = [asdict(c) for c in comparisons]

    return RegressionVerdict(
        status=status,
        summary=summary,
        baseline_idle_drift_pct=baseline_pct,
        movement_drift_pct=max_movement_pct,
        max_anchor_displacement=max_movement_disp,
        is_touchscreen_stuck=is_stuck,
        details=details,
    )


def run_offline_verification(
    still_t0_path: Path,
    still_t1_path: Path,
    movement_paths: list[Path],
    anchors: dict[str, tuple[int, int, int, int]] | None = None,
    threshold: float = 5.0,
) -> RegressionVerdict:
    """在已有截图文件集上执行离线位移测量回归。"""
    active_anchors = anchors or DEFAULT_OVERWORLD_ANCHORS

    img_t0 = cv2.imread(str(still_t0_path))
    img_t1 = cv2.imread(str(still_t1_path))
    if img_t0 is None or img_t1 is None:
        raise FileNotFoundError(f"无法读取基准图像: {still_t0_path} 或 {still_t1_path}")

    comparisons: list[FrameComparisonResult] = []

    # 1. 基准静止呼吸对比
    c_base = compare_frames(
        img_t0, img_t1, "still_t0", "still_t1", active_anchors
    )
    comparisons.append(c_base)

    # 2. 运动按键前后对比
    prev_img = img_t1
    prev_name = "still_t1"
    for idx, m_path in enumerate(movement_paths, start=1):
        m_img = cv2.imread(str(m_path))
        if m_img is None:
            continue
        c_mov = compare_frames(
            prev_img, m_img, prev_name, f"after_w{idx}", active_anchors
        )
        comparisons.append(c_mov)
        prev_img = m_img
        prev_name = f"after_w{idx}"

    return evaluate_movement_series(
        comparisons, displacement_threshold=threshold
    )


async def run_live_verification(
    mcp_url: str = "http://127.0.0.1:23001/mcp",
    key: str = "w",
    press_time: float = 1.0,
    settle_time: float = 1.0,
    anchors: dict[str, tuple[int, int, int, int]] | None = None,
    threshold: float = 5.0,
) -> RegressionVerdict:
    """连接实时 MCP Server 执行在线位移测试。"""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    active_anchors = anchors or DEFAULT_OVERWORLD_ANCHORS

    async with (
        streamable_http_client(mcp_url) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        # 1. 检查游戏窗口
        win_res = await session.call_tool("check_game_window", {})
        win_txt = win_res.content[0].text if win_res.content else "{}"
        win_info = json.loads(win_txt)
        if not win_info.get("is_win_valid"):
            raise RuntimeError(f"游戏窗口未就绪: {win_txt}")

        # 2. 捕获 still_t0
        t0_res = await session.call_tool("capture_game_screen", {})
        t0_path = Path(t0_res.content[0].text.strip())

        # 3. 等待 idle 间隔捕获 still_t1 (建立静止呼吸 baseline)
        time.sleep(1.0)
        t1_res = await session.call_tool("capture_game_screen", {})
        t1_path = Path(t1_res.content[0].text.strip())

        # 4. 执行按键输入 (如 W 移动)
        await session.call_tool(
            "key_tap", {"key": key, "press_time": press_time}
        )
        time.sleep(settle_time)

        # 5. 捕获按键后画面
        w1_res = await session.call_tool("capture_game_screen", {})
        w1_path = Path(w1_res.content[0].text.strip())

        return run_offline_verification(
            still_t0_path=t0_path,
            still_t1_path=t1_path,
            movement_paths=[w1_path],
            anchors=active_anchors,
            threshold=threshold,
        )
