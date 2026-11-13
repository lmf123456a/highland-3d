from dataclasses import dataclass
from math import ceil, floor, isfinite

import numpy as np
import plotly.graph_objects as go
from gpxpy.gpx import GPXTrackPoint
from numpy.typing import NDArray
from rasterio.crs import CRS
from rasterio.errors import CRSError, RasterioError
from rasterio.transform import Affine
from rasterio.warp import transform

from dem_reader import DEMReadError


GridPoint = tuple[float, float]
Vertex = tuple[float, float, float]


@dataclass
class SurfaceGrid:
    crs: CRS
    transform: Affine
    elevations: NDArray[np.float64]

    def cell(self, point: GridPoint) -> tuple[int, int] | None:
        """找到该点所在的有效网格单元，外侧顶点之间才有显示曲面。"""
        column, row = point
        height, width = self.elevations.shape
        if not (0 <= column <= width - 1 and 0 <= row <= height - 1):
            return None
        column_index = min(floor(column), width - 2)
        row_index = min(floor(row), height - 2)
        corners = self.elevations[row_index:row_index + 2, column_index:column_index + 2]
        if np.isfinite(corners).all():
            return column_index, row_index
        return None

    def vertex(self, point: GridPoint, cell: tuple[int, int]) -> Vertex:
        """在 Plotly 使用的两个三角面之一上插值。"""
        column, row = point
        i, j = cell
        u, v = column - i, row - j
        a, b = self.elevations[j, i:i + 2]
        c, d = self.elevations[j + 1, i:i + 2]
        if u + v <= 1:
            elevation = a + (b - a) * u + (c - a) * v
        else:
            elevation = d + (c - d) * (1 - u) + (b - d) * (1 - v)
        x, y = self.transform @ (column, row)
        return x, y, float(elevation)


def edge_breaks(start: GridPoint, end: GridPoint, shape: tuple[int, int]) -> list[float]:
    """按竖线、横线和三角面的对角线切分 GPX 中相邻点间的线段。"""
    height, width = shape
    c0, r0 = start
    c1, r1 = end
    fractions = {0.0, 1.0}
    for first, last, maximum in (
        (c0, c1, width - 1), (r0, r1, height - 1), (c0 + r0, c1 + r1, width + height - 2)
    ):
        low = max(0, floor(min(first, last)) + 1)
        high = min(maximum, ceil(max(first, last)) - 1)
        for boundary in range(low, high + 1):
            fractions.add((boundary - first) / (last - first))
    return sorted(fractions)


def drape_segment(grid: SurfaceGrid, points: list[GridPoint]) -> list[list[Vertex]]:
    """返回一条 GPX 分段在曲面上的连续片段。"""
    if len(points) == 1:
        cell = grid.cell(points[0])
        return [[grid.vertex(points[0], cell)]] if cell is not None else []

    runs: list[list[Vertex]] = []
    current: list[Vertex] = []
    for start, end in zip(points, points[1:]):
        if not all(isfinite(value) for value in (*start, *end)):
            current = []
            continue

        breaks = edge_breaks(start, end, grid.elevations.shape)
        c0, r0 = start
        dc, dr = end[0] - c0, end[1] - r0
        for left, right in zip(breaks, breaks[1:]):
            midpoint = (left + right) / 2
            cell = grid.cell((c0 + dc * midpoint, r0 + dr * midpoint))
            if cell is None:
                current = []
                continue
            if not current:
                current = [grid.vertex((c0 + dc * left, r0 + dr * left), cell)]
                runs.append(current)
            current.append(grid.vertex((c0 + dc * right, r0 + dr * right), cell))
    return runs


def add_track_overlay(
    figure: go.Figure, grid: SurfaceGrid, segments: list[list[GPXTrackPoint]]
) -> None:
    """将 WGS84 轨迹变换到 DEM CRS，贴合到显示的地形曲面。"""
    grid_inverse = ~grid.transform
    # 只为绘图留出少量间隔，悬停显示的仍是插值得到的曲面高程。
    lift = max(float(np.nanmax(grid.elevations) - np.nanmin(grid.elevations)) * 0.001, 0.01)
    for index, segment in enumerate(segments, start=1):
        if not segment:
            continue
        try:
            xs, ys = transform(
                "EPSG:4326", grid.crs,
                [point.longitude for point in segment], [point.latitude for point in segment],
            )
        except (CRSError, RasterioError) as exc:
            raise DEMReadError("无法把 GPX 经纬度转换到 DEM 的坐标参考系。") from exc
        columns, rows = grid_inverse @ (np.asarray(xs), np.asarray(ys))
        runs = drape_segment(grid, list(zip(columns, rows)))
        if not runs:
            continue

        # None 保留同一轨迹段中因缺测或超出图幅而产生的断口。
        vertices = []
        for run in runs:
            if vertices:
                vertices.append((None, None, None))
            vertices.extend(run)
        x, y, elevation = zip(*vertices)
        figure.add_trace(go.Scatter3d(
            x=x,
            y=y,
            z=[height + lift if height is not None else None for height in elevation],
            customdata=elevation,
            name=f"轨迹段 {index}",
            mode="markers" if len(segment) == 1 else "lines",
            line={"color": "#ee6236", "width": 5},
            marker={"color": "#ee6236", "size": 4},
            connectgaps=False,
            hovertemplate="曲面高程 %{customdata:.1f}<extra>%{fullData.name}</extra>",
        ))
    if len(figure.data) == 1:
        raise DEMReadError("GPX 轨迹没有落在可用的地形曲面上，请检查 GPX 和 DEM 的覆盖范围。")
