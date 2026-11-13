from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from math import inf, isfinite
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import CRSError, RasterioError
from rasterio.io import DatasetReader
from rasterio.transform import rowcol
from rasterio.warp import transform


class DEMReadError(ValueError):
    """DEM 输入有问题时，提供可直接显示给用户的错误。"""


@dataclass
class DEMSummary:
    crs: str
    width: int
    height: int
    resolution: tuple[float, float]
    bounds: tuple[float, float, float, float]
    min_elevation: float
    max_elevation: float
    elevation_unit: str | None
    covered_points: int


@contextmanager
def open_dem(path: Path) -> Iterator[DatasetReader]:
    """打开并验证本地单波段高程文件。"""
    if not path.is_file():
        raise DEMReadError(f"DEM 文件不存在或路径不是文件：{path}")

    try:
        with rasterio.open(path) as dem:
            if dem.driver != "GTiff" or dem.count != 1:
                raise DEMReadError("请提供单波段 GeoTIFF 高程文件。")
            if dem.crs is None:
                raise DEMReadError("DEM 缺少坐标参考系（CRS），无法核对轨迹覆盖。")
            if dem.transform.is_degenerate:
                raise DEMReadError("DEM 的栅格变换无效，无法核对轨迹覆盖。")
            yield dem
    except (CRSError, RasterioError) as exc:
        raise DEMReadError(f"无法读取 DEM 或转换坐标，请检查 GeoTIFF 和 CRS：{path}") from exc


def inspect_dem(
    path: Path, track_coordinates: list[tuple[float, float]]
) -> DEMSummary:
    """读取单波段 GeoTIFF，并检查 WGS84 轨迹点（经度、纬度）的覆盖。"""
    with open_dem(path) as dem:
        # 分块读高程，排除 NoData、被掩码的像元和无穷值。
        minimum, maximum = inf, -inf
        for _, window in dem.block_windows(1):
            values = np.ma.masked_invalid(dem.read(1, window=window, masked=True))
            if values.count():
                minimum = min(minimum, float(values.min()))
                maximum = max(maximum, float(values.max()))
        if not isfinite(minimum):
            raise DEMReadError("DEM 没有可用的高程像元。")

        scale, offset = dem.scales[0], dem.offsets[0]
        low, high = sorted((minimum * scale + offset, maximum * scale + offset))
        if not (isfinite(low) and isfinite(high)):
            raise DEMReadError("DEM 高程缩放或偏移无效。")

        covered = 0
        if track_coordinates:
            longitudes, latitudes = zip(*track_coordinates)
            xs, ys = transform("EPSG:4326", dem.crs, longitudes, latitudes)
            if not all(isfinite(x) and isfinite(y) for x, y in zip(xs, ys)):
                raise DEMReadError("部分轨迹点无法转换到 DEM 的坐标参考系。")
            # 由栅格变换计算行列号，覆盖统计只看图幅内是否有该位置。
            rows, columns = rowcol(dem.transform, xs, ys)
            covered = sum(
                0 <= row < dem.height and 0 <= column < dem.width
                for row, column in zip(rows, columns)
            )

        return DEMSummary(
            crs=dem.crs.to_string(),
            width=dem.width,
            height=dem.height,
            resolution=dem.res,
            bounds=tuple(dem.bounds),
            min_elevation=low,
            max_elevation=high,
            elevation_unit=dem.units[0],
            covered_points=covered,
        )
