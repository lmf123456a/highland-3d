import argparse
import sys
from pathlib import Path

from dem_reader import DEMReadError, inspect_dem
from gpx_reader import GPXReadError, read_gpx_segments, summarize_track


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读取 GPX 轨迹，可选检查 DEM 覆盖。")
    parser.add_argument("--gpx", required=True, type=Path, help="GPX 文件路径")
    parser.add_argument("--dem", type=Path, help="可选的 GeoTIFF 高程文件路径")
    args = parser.parse_args(argv)

    try:
        segments = read_gpx_segments(args.gpx)
        summary = summarize_track(segments)
        dem_summary = None
        if args.dem is not None:
            coordinates = [
                (point.longitude, point.latitude)
                for segment in segments
                for point in segment
            ]
            dem_summary = inspect_dem(args.dem, coordinates)
    except (GPXReadError, DEMReadError) as exc:
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

    if dem_summary is not None:
        x_resolution, y_resolution = dem_summary.resolution
        left, bottom, right, top = dem_summary.bounds
        covered = dem_summary.covered_points
        if covered == summary.point_count:
            coverage = "全部覆盖"
        elif covered:
            coverage = "部分覆盖"
        else:
            coverage = "没有覆盖"
        unit = dem_summary.elevation_unit or "文件未标注单位"

        print(f"\nDEM CRS：{dem_summary.crs}")
        print(f"DEM 尺寸：{dem_summary.width} × {dem_summary.height} 像元")
        print(f"DEM 分辨率（CRS 单位/像元）：x={x_resolution:.9g}, y={y_resolution:.9g}")
        print(
            f"DEM 边界（原 CRS）：left={left:.9g}, bottom={bottom:.9g}, "
            f"right={right:.9g}, top={top:.9g}"
        )
        print(
            f"DEM 高程范围：{dem_summary.min_elevation:.6g} 到 "
            f"{dem_summary.max_elevation:.6g}（{unit}）"
        )
        print(f"DEM 图幅覆盖：{coverage}（{covered}/{summary.point_count} 个轨迹点）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
