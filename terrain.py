import argparse
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from rasterio.enums import Resampling
from rasterio.errors import CRSError, RasterioError
from rasterio.transform import Affine

from dem_reader import DEMReadError, open_dem
from gpx_reader import GPXReadError, read_gpx_segments, summarize_track
from route_terrain import image_colors, read_route_grid
from track_overlay import SurfaceGrid, add_track_overlay


MAX_GRID_SIZE = 300


def build_terrain(
    dem_path: Path, gpx_path: Path | None = None, *,
    full_tile: bool = False, imagery: Path | None = None,
) -> go.Figure:
    """从 DEM 像元生成 Plotly 地形曲面，可选叠加轨迹。"""
    segments = read_gpx_segments(gpx_path) if gpx_path is not None else None
    track = summarize_track(segments) if segments is not None else None
    crop = track is not None and not full_tile
    if imagery is not None and not crop:
        raise DEMReadError("使用 --imagery 时需要 --gpx 的路线裁剪模式。")

    with open_dem(dem_path) as dem:
        if min(dem.width, dem.height) < 2:
            raise DEMReadError("生成曲面至少需要 2 行、2 列高程像元。")
        unit = dem.units[0]
        if crop:
            grid = read_route_grid(dem, track)
        else:
            ratio = min(1, MAX_GRID_SIZE / max(dem.width, dem.height))
            width = max(2, round(dem.width * ratio))
            height = max(2, round(dem.height * ratio))
            samples = dem.read(
                1, out_shape=(height, width), masked=True, resampling=Resampling.nearest
            )
            with np.errstate(invalid="ignore", over="ignore"):
                z = samples.astype(np.float64).filled(np.nan) * dem.scales[0] + dem.offsets[0]
            transform = (
                dem.transform @ Affine.scale(dem.width / width, dem.height / height)
                @ Affine.translation(0.5, 0.5)
            )
            grid = SurfaceGrid(dem.crs, transform, z)

    elevations = grid.elevations
    elevations[~np.isfinite(elevations)] = np.nan
    valid = np.isfinite(elevations)
    cells = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:] & valid[1:, 1:]
    if not cells.any():
        raise DEMReadError("显示网格没有足够相邻的有效高程像元生成曲面。")
    height, width = elevations.shape
    columns, rows = np.meshgrid(np.arange(width), np.arange(height))
    x, y = grid.transform @ (columns, rows)
    crs = grid.crs.to_string()
    if crop:
        x_title, y_title, height_title = "东向（m）", "北向（m）", "高程（m）"
    else:
        x_title, y_title = ("经度（°）", "纬度（°）") if grid.crs.is_geographic else ("X", "Y")
        height_title = f"高程（{unit}）" if unit else "高程"

    colors = dict(
        colorscale=[[0, "#21463e"], [0.3, "#4c7759"], [0.65, "#a7a079"], [1, "#f0ead8"]],
        colorbar={"title": height_title, "thickness": 16},
        hovertemplate=(
            f"{x_title} %{{x:.6g}}<br>{y_title} %{{y:.6g}}<br>"
            f"{height_title} %{{z:.1f}}<extra></extra>"
        ),
    )
    if segments is None:
        figure = go.Figure(go.Surface(x=x, y=y, z=elevations, connectgaps=False, **colors))
    else:
        # 显式定义三角面，确保 Plotly 画出的曲面与轨迹插值使用同一几何。
        cell_rows, cell_columns = np.nonzero(cells)
        a = cell_rows * width + cell_columns
        b, c, d = a + 1, a + width, a + width + 1
        # 缺测顶点没有任何三角面引用，仍给 WebGL 提供有限值。
        heights = np.where(valid, elevations, np.nanmin(elevations)).ravel()
        material = (
            {
                "vertexcolor": image_colors(imagery, grid), "showscale": False,
                # 卫星影像已经带有日照与阴影，避免额外光照改变地表颜色。
                "lighting": {"ambient": 1, "diffuse": 0, "specular": 0, "fresnel": 0},
            }
            if imagery else {"intensity": heights, "showscale": True}
        )
        figure = go.Figure(go.Mesh3d(
            x=x.ravel(), y=y.ravel(), z=heights,
            i=np.concatenate((a, d)), j=np.concatenate((c, b)), k=np.concatenate((b, c)),
            name="地形", showlegend=False, **material, **colors,
        ))
        add_track_overlay(figure, grid, segments, metre_units=crop)
    subtitle = f"{crs} · 显示网格 {width} × {height}"
    if crop:
        subtitle += f" · 约 {grid.transform.a:.0f} × {-grid.transform.e:.0f} m 间距 · 真实比例"
    aspect = {"aspectmode": "data"} if crop else {
        "aspectmode": "manual", "aspectratio": {"x": 1, "y": 1, "z": 0.28},
    }
    figure.update_layout(
        title={"text": "HIGHLAND 3D · 地形与轨迹" if gpx_path else "HIGHLAND 3D · DEM 地形", "subtitle": {
            "text": f"{subtitle} · 拖动旋转，滚轮缩放"
        }},
        template="plotly_white",
        paper_bgcolor="#f6f7f2",
        font={"family": "Arial, Microsoft YaHei, sans-serif", "color": "#223631"},
        margin={"l": 10, "r": 20, "t": 85, "b": 10},
        scene={
            "xaxis_title": x_title,
            "yaxis_title": y_title,
            "zaxis_title": height_title,
            **aspect,
            "camera": {"eye": {"x": 1.45, "y": -1.65, "z": 1.05}},
        },
    )
    return figure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出离线三维地形，可选叠加 GPX 轨迹。")
    parser.add_argument("--dem", type=Path, required=True, help="GeoTIFF 高程文件路径")
    parser.add_argument("--gpx", type=Path, help="要叠加的 GPX 文件路径")
    parser.add_argument("--full-tile", action="store_true", help="沿用整图幅预览")
    parser.add_argument("--imagery", type=Path, help="可选的本地 RGB GeoTIFF 影像")
    parser.add_argument("--output", type=Path, help="输出 HTML 路径")
    args = parser.parse_args(argv)
    default_output = "output/terrain-with-track.html" if args.gpx else "output/terrain.html"
    output = args.output or Path(default_output)

    if output.suffix.lower() != ".html":
        print("错误：输出路径须以 .html 结尾。", file=sys.stderr)
        return 1
    try:
        inputs = [source for source in (args.dem, args.gpx, args.imagery) if source is not None]
        for source in inputs:
            if output.resolve() == source.resolve() or (
                output.exists() and source.exists() and output.samefile(source)
            ):
                raise DEMReadError("输出路径与输入文件相同，请更换输出路径。")
        figure = build_terrain(args.dem, args.gpx, full_tile=args.full_tile, imagery=args.imagery)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(
            output, include_plotlyjs=True,
            config={"scrollZoom": True, "displaylogo": False},
        )
    except (DEMReadError, GPXReadError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except (CRSError, RasterioError):
        print("错误：无法读取或转换地理栅格，请检查文件和坐标参考系。", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"错误：无法访问输入或输出文件。{exc}", file=sys.stderr)
        return 1

    print(f"三维地形已保存：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
