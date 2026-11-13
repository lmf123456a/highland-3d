import argparse
import sys
from pathlib import Path

from gpx_reader import GPXReadError, read_gpx_segments, summarize_track


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读取 GPX 轨迹并打印坐标摘要。")
    parser.add_argument("--gpx", required=True, type=Path, help="GPX 文件路径")
    args = parser.parse_args(argv)

    try:
        segments = read_gpx_segments(args.gpx)
        summary = summarize_track(segments)
    except GPXReadError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"轨迹点数：{summary.point_count}")
    print(f"轨迹段数：{summary.segment_count}")
    print(f"起点：latitude={summary.start.latitude}, longitude={summary.start.longitude}")
    print(f"终点：latitude={summary.end.latitude}, longitude={summary.end.longitude}")
    print("bbox (WGS84，度)：")
    for direction, value in summary.bbox.items():
        print(f"  {direction}={value}")
    print(f"海拔数据：{'存在' if summary.has_elevation else '缺失'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
