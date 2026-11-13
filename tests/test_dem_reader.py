from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from dem_reader import DEMReadError, inspect_dem
from main import main


DEMO_GPX = Path(__file__).resolve().parents[1] / "samples" / "demo.gpx"


def write_dem(
    path: Path,
    *,
    crs: str | None = "EPSG:4326",
    west: float = 0,
    north: float = 2,
    pixel_size: float = 1,
    values: list[list[float]] | None = None,
    scale: float = 1,
    offset: float = 0,
) -> Path:
    if values is None:
        values = [[0, 5], [8, -9999]]
    elevations = np.array(values, dtype="float32")
    height, width = elevations.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype=elevations.dtype,
        crs=crs,
        nodata=-9999,
        transform=Affine(pixel_size, 0, west, 0, -pixel_size, north),
    ) as dem:
        dem.write(elevations, 1)
        dem.scales = (scale,)
        dem.offsets = (offset,)
        dem.set_band_unit(1, "m")
    return path


def test_dem_metadata_and_partial_coverage(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "elevation.tif", scale=2, offset=10)

    summary = inspect_dem(path, [(0.5, 1.5), (1.5, 0.5), (2, 1), (1, 0)])

    assert summary.crs == "EPSG:4326"
    assert (summary.width, summary.height) == (2, 2)
    assert summary.resolution == (1, 1)
    assert summary.bounds == (0, 0, 2, 2)
    assert (summary.min_elevation, summary.max_elevation) == (10, 26)
    assert summary.elevation_unit == "m"
    # 第二个点在 NoData 像元内，也在图幅内。
    assert summary.covered_points == 2


def test_transforms_gpx_points_to_projected_crs(tmp_path: Path) -> None:
    path = write_dem(
        tmp_path / "projected.tif", crs="EPSG:3857", west=100000, north=200000,
        pixel_size=10000,
    )

    summary = inspect_dem(path, [(1, 1.7), (0.5, 1.7)])

    assert summary.crs == "EPSG:3857"
    assert summary.covered_points == 1


def test_missing_crs_is_reported(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "no_crs.tif", crs=None)

    with pytest.raises(DEMReadError, match="缺少坐标参考系"):
        inspect_dem(path, [(1, 1)])


def test_dem_without_valid_elevations_is_reported(tmp_path: Path) -> None:
    path = write_dem(
        tmp_path / "no_data.tif", values=[[-9999, float("nan")], [float("inf"), -9999]],
    )

    with pytest.raises(DEMReadError, match="没有可用的高程像元"):
        inspect_dem(path, [(1, 1)])


def test_broken_dem_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.tif"
    path.write_bytes(b"invalid raster")

    with pytest.raises(DEMReadError, match="无法读取 DEM"):
        inspect_dem(path, [(1, 1)])


@pytest.mark.parametrize(
    ("west", "expected"),
    [(100, "全部覆盖（4/4"), (100.2, "部分覆盖（3/4"), (90, "没有覆盖（0/4")],
)
def test_cli_prints_dem_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], west: float, expected: str,
) -> None:
    path = write_dem(tmp_path / "elevation.tif", west=west, north=31)

    assert main(["--gpx", str(DEMO_GPX), "--dem", str(path)]) == 0
    captured = capsys.readouterr()

    assert f"DEM 图幅覆盖：{expected}" in captured.out
    assert "DEM CRS：EPSG:4326" in captured.out
    assert captured.err == ""


def test_cli_reports_missing_dem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--gpx", str(DEMO_GPX), "--dem", str(tmp_path / "missing.tif")]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "错误：DEM 文件不存在" in captured.err
