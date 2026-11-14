from math import floor, hypot, sqrt
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import DatasetReader
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform

from dem_reader import DEMReadError
from gpx_reader import TrackSummary
from track_overlay import SurfaceGrid


MAX_ROUTE_VERTICES = 300_000


def read_route_grid(dem: DatasetReader, track: TrackSummary) -> SurfaceGrid:
    """按路线包围盒留出余量，在本地 UTM 米制网格上读取高程。"""
    west, south, east, north = (track.bbox[key] for key in ("west", "south", "east", "north"))
    if east - west > 6 or south < -80 or north > 84:
        raise DEMReadError("路线超出本地 UTM 预览范围，可用 --full-tile 查看原图幅。")
    lon, lat = (west + east) / 2, (south + north) / 2
    zone = min(60, floor((lon + 180) / 6) + 1)
    crs = CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)
    xs, ys = transform("EPSG:4326", crs, [west, east, west, east], [south, south, north, north])
    left, bottom, right, top = min(xs), min(ys), max(xs), max(ys)
    padding = max(2_000, 0.2 * max(right - left, top - bottom))
    left, bottom, right, top = left - padding, bottom - padding, right + padding, top + padding
    span_x, span_y = right - left, top - bottom

    # 在路线附近比较源栅格相邻像元的距离，避免把插值误当成新增细节。
    source_x, source_y = transform("EPSG:4326", dem.crs, [lon], [lat])
    corners = [(source_x[0], source_y[0])]
    corners.append((source_x[0] + dem.transform.a, source_y[0] + dem.transform.d))
    corners.append((source_x[0] + dem.transform.b, source_y[0] + dem.transform.e))
    x, y = transform(dem.crs, crs, *zip(*corners))
    source_step = max(hypot(x[i] - x[0], y[i] - y[0]) for i in (1, 2))
    display_step = max(source_step, sqrt(span_x * span_y / MAX_ROUTE_VERTICES))
    width, height = max(2, floor(span_x / display_step)), max(2, floor(span_y / display_step))
    if width * height > MAX_ROUTE_VERTICES:
        raise DEMReadError("路线过长，超出当前显示网格上限，可用 --full-tile 查看原图幅。")
    affine = Affine(span_x / width, 0, left, 0, -span_y / height, top)

    with WarpedVRT(
        dem, crs=crs, transform=affine, width=width, height=height,
        nodata=np.nan, dtype="float64", resampling=Resampling.bilinear,
    ) as warped:
        z = warped.read(1, masked=True).filled(np.nan)

    unit = (dem.units[0] or "m").strip().lower()
    if unit in {"m", "meter", "meters", "metre", "metres"}:
        metres = 1.0
    elif unit in {"ft", "foot", "feet", "international foot"}:
        metres = 0.3048
    elif unit in {"us survey foot", "us survey feet", "us_survey_foot"}:
        metres = 1200 / 3937
    else:
        raise DEMReadError(f"无法把 DEM 高程单位 {dem.units[0]} 转换为米。")
    z = (z * dem.scales[0] + dem.offsets[0]) * metres
    return SurfaceGrid(crs, affine @ Affine.translation(0.5, 0.5), z)


def image_colors(path: Path, grid: SurfaceGrid) -> np.ndarray:
    """把本地 8 位 RGB GeoTIFF 与地形网格对齐，返回逐顶点颜色。"""
    if not path.is_file():
        raise DEMReadError(f"影像文件不存在：{path}")
    height, width = grid.elevations.shape
    affine = grid.transform @ Affine.translation(-0.5, -0.5)
    with rasterio.open(path) as image:
        if image.driver != "GTiff" or image.crs is None or image.count != 3:
            raise DEMReadError("影像须是带坐标参考系的三波段 RGB GeoTIFF。")
        if image.dtypes != ("uint8",) * 3:
            raise DEMReadError("影像须使用 8 位 RGB 波段。")
        with WarpedVRT(
            image, crs=grid.crs, transform=affine, width=width, height=height,
            add_alpha=True, resampling=Resampling.bilinear,
        ) as warped:
            rgb = warped.read((1, 2, 3))
            covered = warped.read(4) > 0
    if not covered[np.isfinite(grid.elevations)].any():
        raise DEMReadError("影像与有效地形没有重叠。")
    rgb[:, ~covered] = np.array([[149], [154], [138]], dtype=np.uint8)
    return rgb.reshape(3, -1).T.copy()
