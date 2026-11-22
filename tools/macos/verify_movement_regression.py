#!/usr/bin/env python3
"""macOS PlayCover ZZZ 输入模式与位移回归测试 CLI。

使用方法:
  uv run python3 tools/macos/verify_movement_regression.py --mode offline
  uv run python3 tools/macos/verify_movement_regression.py --mode offline --json
  uv run python3 tools/macos/verify_movement_regression.py --mode live
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from one_dragon.utils.movement_verifier import (
    run_live_verification,
    run_offline_verification,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="macOS PlayCover ZZZ 输入模式与位移回归测试工具"
    )
    parser.add_argument(
        "--mode",
        choices=["offline", "live"],
        default="offline",
        help="运行模式: offline (分析静态图片) 或 live (在线调 MCP 发送按键)",
    )
    parser.add_argument(
        "--t0",
        type=Path,
        default=Path("plans/reports/still_t0.png"),
        help="基准帧 t0 路径 (默认 plans/reports/still_t0.png)",
    )
    parser.add_argument(
        "--t1",
        type=Path,
        default=Path("plans/reports/still_t1.png"),
        help="基准帧 t1 路径 (默认 plans/reports/still_t1.png)",
    )
    parser.add_argument(
        "--movement",
        type=Path,
        nargs="+",
        default=[
            Path("plans/reports/after_w1.png"),
            Path("plans/reports/after_w2.png"),
        ],
        help="移动测试帧列表 (默认 after_w1.png after_w2.png)",
    )
    parser.add_argument(
        "--mcp-url",
        default="http://127.0.0.1:23001/mcp",
        help="MCP Server URL",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="位移判定阈值像素 (默认 5.0)",
    )
    parser.add_argument(
        "--json", action="store_true", help="以 JSON 格式输出测试结果"
    )

    args = parser.parse_args()

    if args.mode == "offline":
        verdict = run_offline_verification(
            still_t0_path=args.t0,
            still_t1_path=args.t1,
            movement_paths=args.movement,
            threshold=args.threshold,
        )
    else:
        verdict = asyncio.run(
            run_live_verification(
                mcp_url=args.mcp_url, threshold=args.threshold
            )
        )

    if args.json:
        print(json.dumps(asdict(verdict), ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print(f"ZZZ Movement Regression Verdict: [{verdict.status}]")
        print("=" * 60)
        print(f"Summary: {verdict.summary}")
        print(f"Baseline Idle Drift: {verdict.baseline_idle_drift_pct:.2f}%")
        print(f"Movement Max Drift: {verdict.movement_drift_pct:.2f}%")
        print(f"Max Anchor Displacement: {verdict.max_anchor_displacement:.2f}px")
        print(f"Touchscreen Locked: {verdict.is_touchscreen_stuck}")
        print("\nAnchor Details:")
        for comp in verdict.details:
            print(
                f"\n--- {comp['frame_a_name']} vs {comp['frame_b_name']} (Changed: {comp['changed_percent']:.2f}%) ---"
            )
            for a in comp["anchors"]:
                print(
                    f"  * {a['name']:<20}: pos={a['found_pos']} delta=({a['delta_x']}, {a['delta_y']}) "
                    f"dist={a['displacement']:.2f}px score={a['confidence']:.4f}"
                )


if __name__ == "__main__":
    main()
