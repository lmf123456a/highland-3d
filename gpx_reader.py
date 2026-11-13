from dataclasses import dataclass
from io import StringIO
from math import isfinite
from pathlib import Path
from xml.etree.ElementTree import ParseError, iterparse

import gpxpy
from gpxpy.gpx import GPXException, GPXTrackPoint, GPXXMLSyntaxException


class GPXReadError(ValueError):
    """GPX 输入有问题时，提供可直接显示给用户的错误。"""


@dataclass
class TrackSummary:
    point_count: int
    segment_count: int
    start: GPXTrackPoint
    end: GPXTrackPoint
    bbox: dict[str, float]
    has_elevation: bool


def read_gpx_segments(path: Path) -> list[list[GPXTrackPoint]]:
    """按文件顺序读取每个轨迹段，并保留段内的有效点。"""
    try:
        xml = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise GPXReadError(f"文件不存在：{path}") from exc
    except UnicodeDecodeError as exc:
        raise GPXReadError(f"无法用 UTF-8 读取文件：{path}") from exc
    except OSError as exc:
        raise GPXReadError(f"无法读取文件：{path}。请检查路径和读取权限。") from exc

    if not xml.strip():
        raise GPXReadError(f"文件为空：{path}")

    try:
        # gpxpy 负责读取轨迹，这里只检查 XML 的根元素。
        _, root = next(iterparse(StringIO(xml), events=("start",)))
        if root.tag.rsplit("}", 1)[-1] != "gpx":
            raise GPXReadError("文件不是 GPX，根元素应为 gpx。")
    except ParseError as exc:
        raise GPXReadError("GPX XML 格式错误，请检查文件是否损坏。") from exc

    try:
        gpx = gpxpy.parse(xml)
    except GPXXMLSyntaxException as exc:
        raise GPXReadError("GPX XML 格式错误，请检查文件是否损坏。") from exc
    except (GPXException, ValueError) as exc:
        raise GPXReadError("GPX 字段格式错误，请检查文件中的经纬度等字段。") from exc

    segments = []
    for track in gpx.tracks:
        for segment in track.segments:
            valid_points = [
                point
                for point in segment.points
                if -90 <= point.latitude <= 90 and -180 <= point.longitude < 180
            ]
            segments.append(valid_points)
    return segments


def summarize_track(segments: list[list[GPXTrackPoint]]) -> TrackSummary:
    """汇总所有有效点，保留原有的分段数据。"""
    # 这里只展开列表做统计，segments 仍然保留每段的边界。
    points = [point for segment in segments for point in segment]
    if not points:
        raise GPXReadError("文件中没有有效轨迹点，请检查 trk、trkseg 和 trkpt。")

    return TrackSummary(
        point_count=len(points),
        segment_count=len(segments),
        start=points[0],
        end=points[-1],
        bbox={
            "west": min(point.longitude for point in points),
            "south": min(point.latitude for point in points),
            "east": max(point.longitude for point in points),
            "north": max(point.latitude for point in points),
        },
        has_elevation=any(
            point.elevation is not None and isfinite(point.elevation)
            for point in points
        ),
    )
