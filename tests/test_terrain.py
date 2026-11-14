from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from dem_reader import DEMReadError
from terrain import MAX_GRID_SIZE, build_terrain, main


def write_dem(
    path: Path, values: np.ndarray, *, crs: str = "EPSG:4326",
    transform: Affine = Affine(0.1, 0, 100, 0, -0.1, 31),
) -> Path:
    height, width = values.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999,
    ) as dem:
        dem.write(values, 1)
        dem.scales = (2,)
        dem.offsets = (10,)
    return path


def test_surface_uses_dem_coordinates_elevations_and_mask(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "terrain.tif", np.array([[1, 2, 3], [4, 5, -9999]]))

    surface, = build_terrain(path).data

    assert surface.type == "surface"
    np.testing.assert_allclose(surface.x[0], [100.05, 100.15, 100.25])
    np.testing.assert_allclose(surface.y[:, 0], [30.95, 30.85])
    np.testing.assert_allclose(surface.z, [[12, 14, 16], [18, 20, np.nan]])
    assert surface.connectgaps is False


def test_large_dem_is_downsampled_proportionally(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "large.tif", np.ones((350, 600)))

    surface, = build_terrain(path).data

    assert surface.z.shape == (175, MAX_GRID_SIZE)
    assert np.all(surface.z == 12)


def test_dem_without_a_valid_surface_is_reported(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "empty.tif", np.full((2, 2), -9999))

    with pytest.raises(DEMReadError, match="没有足够相邻"):
        build_terrain(path)


def test_cli_exports_standalone_html(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "terrain.tif", np.ones((2, 2)))
    output = tmp_path / "generated" / "terrain.html"

    assert main(["--dem", str(path), "--output", str(output)]) == 0

    html = output.read_text(encoding="utf-8")
    assert "Plotly.newPlot" in html
    assert '"type":"surface"' in html
    assert "plotly.js v" in html
    assert "<script src=" not in html


def test_cli_refuses_to_overwrite_input(tmp_path: Path) -> None:
    path = write_dem(tmp_path / "terrain.html", np.ones((2, 2)))
    original = path.read_bytes()

    assert main(["--dem", str(path), "--output", str(path)]) == 1
    assert path.read_bytes() == original


def write_track(path: Path, *segments: list[tuple[float, float]]) -> Path:
    tracks = []
    for segment in segments:
        points = "".join(f'<trkpt lon="{x}" lat="{y}"/>' for x, y in segment)
        tracks.append(f"<trkseg>{points}</trkseg>")
    path.write_text(f"<gpx><trk>{''.join(tracks)}</trk></gpx>", encoding="utf-8")
    return path


def test_track_follows_mesh_triangles_and_keeps_segments(tmp_path: Path) -> None:
    dem = write_dem(tmp_path / "terrain.tif", np.array([[0, 0], [0, 100]]))
    gpx = write_track(
        tmp_path / "track.gpx", [(100.07, 30.93), (100.13, 30.87)], [(100.1, 30.92)],
    )

    mesh, line, marker = build_terrain(dem, gpx, full_tile=True).data

    assert mesh.type == "mesh3d"
    assert list(zip(mesh.i, mesh.j, mesh.k)) == [(0, 2, 1), (3, 1, 2)]
    assert [line.name, marker.name] == ["轨迹段 1", "轨迹段 2"]
    assert [line.mode, marker.mode] == ["lines", "markers"]
    np.testing.assert_allclose(line.x, [100.07, 100.10, 100.13])
    np.testing.assert_allclose(line.y, [30.93, 30.90, 30.87])
    np.testing.assert_allclose(line.customdata, [10, 10, 130])
    np.testing.assert_allclose(np.asarray(line.z) - line.customdata, 0.2)


def test_sparse_track_is_clipped_and_breaks_at_nodata(tmp_path: Path) -> None:
    values = np.ones((2, 6))
    values[:, 2] = -9999
    dem = write_dem(tmp_path / "terrain.tif", values)
    gpx = write_track(tmp_path / "track.gpx", [(99.9, 30.9), (100.7, 30.9)])

    mesh, line = build_terrain(dem, gpx, full_tile=True).data

    assert line.connectgaps is False
    assert not {2, 8}.intersection((*mesh.i, *mesh.j, *mesh.k))
    gap = line.x.index(None)
    np.testing.assert_allclose([line.x[0], line.x[gap - 1]], [100.05, 100.15])
    np.testing.assert_allclose([line.x[gap + 1], line.x[-1]], [100.35, 100.55])


def test_track_is_transformed_to_projected_dem(tmp_path: Path) -> None:
    dem = write_dem(
        tmp_path / "terrain.tif", np.ones((3, 3)), crs="EPSG:3857",
        transform=Affine(1000, 0, 110000, 0, -1000, 2000),
    )
    gpx = write_track(tmp_path / "track.gpx", [(1, 0), (1.005, 0)])

    _, line = build_terrain(dem, gpx, full_tile=True).data

    np.testing.assert_allclose([line.x[0], line.x[-1]], [111319.490793, 111876.088247])
    np.testing.assert_allclose(line.y, 0)


def test_cli_reports_track_without_overlap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dem = write_dem(tmp_path / "terrain.tif", np.ones((2, 2)))
    gpx = write_track(tmp_path / "track.gpx", [(1, 1), (2, 2)])
    output = tmp_path / "terrain.html"

    assert main(["--dem", str(dem), "--gpx", str(gpx), "--full-tile", "--output", str(output)]) == 1
    assert "没有落在可用的地形曲面" in capsys.readouterr().err
    assert not output.exists()


def test_route_crop_uses_native_spacing_and_metre_axes(tmp_path: Path) -> None:
    affine = Affine(30, 0, 500000, 0, -30, 12000)
    values = np.full((400, 400), 40, dtype="float32")
    dem = write_dem(
        tmp_path / "terrain.tif", values, crs="EPSG:32631", transform=affine,
    )
    with rasterio.open(dem, "r+") as dataset:
        dataset.set_band_unit(1, "ft")
    gpx = write_track(tmp_path / "route.gpx", [(3.04, 0.052), (3.052, 0.056)])

    figure = build_terrain(dem, gpx)
    mesh, line = figure.data

    assert figure.layout.scene.aspectmode == "data"
    assert figure.layout.scene.zaxis.title.text == "高程（m）"
    assert 4000 < np.ptp(mesh.x) < 5500
    assert 4000 < np.ptp(mesh.y) < 4600
    assert mesh.x[1] - mesh.x[0] == pytest.approx(30, abs=0.5)
    np.testing.assert_allclose(mesh.z, 90 * 0.3048)
    np.testing.assert_allclose(np.array(line.z) - line.customdata, 1)


def test_local_rgb_changes_colors_without_changing_geometry(tmp_path: Path) -> None:
    affine = Affine(0.002, 0, 2.94, 0, -0.002, 0.12)
    dem = write_dem(tmp_path / "terrain.tif", np.ones((60, 60)), transform=affine)
    gpx = write_track(tmp_path / "route.gpx", [(3, 0.05), (3.01, 0.06)])
    rgb = tmp_path / "rgb.tif"
    with rasterio.open(
        rgb, "w", driver="GTiff", count=3, height=60, width=60, dtype="uint8",
        crs="EPSG:4326", transform=affine,
    ) as image:
        image.write(np.broadcast_to(np.array([23, 67, 134], dtype=np.uint8)[:, None, None], (3, 60, 60)))

    ground = build_terrain(dem, gpx)
    colored = build_terrain(dem, gpx, imagery=rgb)

    terrain = colored.data[0]
    assert terrain.showscale is False
    np.testing.assert_array_equal(terrain.vertexcolor[0], [23, 67, 134])
    np.testing.assert_array_equal(terrain.z, ground.data[0].z)
    np.testing.assert_array_equal(terrain.i, ground.data[0].i)
    np.testing.assert_array_equal(colored.data[1].z, ground.data[1].z)
