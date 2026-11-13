# HIGHLAND 3D

HIGHLAND 3D 可以读取 GPX 轨迹，检查本地 GeoTIFF 高程文件是否覆盖轨迹，并生成带轨迹的可交互三维地形。

## 安装

准备 Python 3.11 或 3.12。在 Windows PowerShell 中打开项目目录，运行以下命令创建虚拟环境并安装依赖。

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows 上如果 `python --version` 打开应用商店或提示找不到 Python，可以安装 [Python](https://www.python.org/downloads/windows/)，重新打开 PowerShell 后再检查版本。已装有 Python Launcher 时，也可以用 `py -3.12 -m venv .venv` 创建环境，安装的是 3.11 时用 `py -3.11`。

## 运行 GPX 摘要（M0-1）

```powershell
.\.venv\Scripts\python.exe main.py --gpx samples/demo.gpx
```

激活虚拟环境后，可以直接运行 `python main.py --gpx samples/demo.gpx`。macOS 和 Linux 上用 `python3 -m venv .venv` 创建环境，虚拟环境的解释器路径为 `.venv/bin/python`。

`samples/demo.gpx` 是合成演示数据，坐标和海拔都是模拟值，不代表真实徒步路线。示例应输出 4 个点、2 个段和“海拔数据：存在”。请把个人真实轨迹放在 Git 已忽略的 `data/private/` 目录中。

### GPX 读取规则

- 支持 UTF-8 编码的 `trk / trkseg / trkpt` 轨迹。暂不统计路线 `rte / rtept` 或独立航点 `wpt`。
- 段数按文件中的 `trkseg` 计，包含空段。每段的有效点单独保存，起终点取文件顺序中的第一个和最后一个有效点。
- 数值超出 GPX 经纬度范围的点不计入统计。经纬度属性缺失或无法解析为数字时，程序会提示字段格式错误。完全没有有效点时，程序会提示检查轨迹结构。
- bbox 以 WGS84 十进制度输出，顺序为 `west`（最小经度）、`south`（最小纬度）、`east`（最大经度）、`north`（最大纬度）。经度直接取最小值和最大值，跨越 180° 经线的轨迹会得到较宽的框。 [GPX 1.1 格式说明](https://www.topografix.com/GPX/1/1/)
- 只要有一个有效轨迹点带有限数值的海拔，就显示“存在”。所有有效点都缺少海拔时显示“缺失”，仍会输出坐标摘要。

## 检查 DEM 图幅覆盖（M0-2）

准备单波段高程 GeoTIFF 和同一地区的 GPX。将数据放进 `data/private/`，在命令中换成自己的文件名。

```powershell
.\.venv\Scripts\python.exe main.py --gpx "data/private/track.gpx" --dem "data/private/elevation.tif"
```

- **CRS** 是坐标参考系。程序把 GPX 的 WGS84 经度和纬度转换到 DEM 的 CRS，再计算点落在哪一行、哪一列。
- **分辨率**按 CRS 的单位显示。经纬度坐标系的栅格通常用度/像元，投影坐标系则用该 CRS 的线性单位，例如米/像元。
- **高程范围**统计整个图幅中的有效高程，排除 NoData、掩码和非有限值。文件未标注高程单位时，程序会显示“文件未标注单位”。
- **图幅覆盖**报告落在栅格内的轨迹点数量，并区分全部、部分和没有覆盖。落在 NoData 像元上的点也计入图幅覆盖。

真实数据验证使用 Copernicus DEM GLO-30 Public 的公开 GeoTIFF。它提供约 30 米级的地表高程，可能包含植被和建筑物的高度。获取数据后可在 `data/private/` 保存来源和瓦片编号，发布任何数据或衍生结果前按数据集许可核对署名要求。 [数据来源](https://registry.opendata.aws/copernicus-dem/) · [许可和署名](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)

## 生成离线三维地形（M0-3）

安装或更新 `requirements.txt` 中的依赖后，运行下面的命令。`--dem` 指向本地单波段 GeoTIFF，`--output` 可省略，默认生成 `output/terrain.html`。

```powershell
.\.venv\Scripts\python.exe terrain.py --dem "data/private/elevation.tif" --output "output/terrain.html"
```

用支持 WebGL 的浏览器打开生成的 HTML。拖动旋转，滚轮缩放，悬停查看坐标与高程。文件内嵌 Plotly，可以离线打开。

程序用最近邻方法将栅格最长边缩至最多 300 个采样点，保留缺测处的空洞。显示的网格坐标来自 GeoTIFF 的仿射变换，高程来自栅格像元。视图采用独立的横向和纵向显示比例，适合观察起伏。高程单位以文件元数据为准，Copernicus GLO-30 的高程单位可查产品说明。 [Rasterio 重采样](https://rasterio.readthedocs.io/en/stable/topics/resampling.html) · [Copernicus 产品规格](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)

## 叠加 GPX 轨迹（M0-4）

在地形命令中加上 `--gpx`，默认输出到 `output/terrain-with-track.html`。

```powershell
.\.venv\Scripts\python.exe terrain.py --dem "data/private/elevation.tif" --gpx "data/private/track.gpx"
Start-Process .\output\terrain-with-track.html
```

程序将 WGS84 经纬度转换到 DEM 的 CRS，在实际显示的地形三角面上插值，并在轨迹穿过三角面边界时补点。橙色线条会略抬高以便看清，悬停显示插值所得的曲面高程。GPX 的海拔字段不参与贴地计算。不同 GPX 分段以及缺测或超出显示曲面的区间会断开。

导出的 HTML 包含轨迹坐标，默认存放在 Git 忽略的 `output/`。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试使用合成 GPX 和临时生成的 GeoTIFF，无需下载真实高程数据。
