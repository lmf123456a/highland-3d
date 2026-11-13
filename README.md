# HIGHLAND 3D

M0-1 从 GPX 轨迹文件中读取有效轨迹点，并在终端显示点数、段数、起终点、边界框和海拔数据状态。

## 安装

准备 Python 3.11 或 3.12。在 Windows PowerShell 中打开项目目录，运行以下命令创建虚拟环境并安装依赖。

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows 上如果 `python --version` 打开应用商店或提示找不到 Python，可以安装 [Python](https://www.python.org/downloads/windows/)，重新打开 PowerShell 后再检查版本。已装有 Python Launcher 时，也可以用 `py -3.12 -m venv .venv` 创建环境，安装的是 3.11 时用 `py -3.11`。

## 运行和测试

```powershell
.\.venv\Scripts\python.exe main.py --gpx samples/demo.gpx
.\.venv\Scripts\python.exe -m pytest -q
```

激活虚拟环境后，可以直接运行 `python main.py --gpx samples/demo.gpx` 和 `pytest -q`。macOS 和 Linux 上用 `python3 -m venv .venv` 创建环境，虚拟环境的解释器路径为 `.venv/bin/python`。

`samples/demo.gpx` 是合成演示数据，坐标和海拔都是模拟值，不代表真实徒步路线。示例应输出 4 个点、2 个段和“海拔数据：存在”。请把个人真实轨迹放在 Git 已忽略的 `data/private/` 目录中。

## 读取规则

- 支持 UTF-8 编码的 `trk / trkseg / trkpt` 轨迹。暂不统计路线 `rte / rtept` 或独立航点 `wpt`。
- 段数按文件中的 `trkseg` 计，包含空段。每段的有效点单独保存，起终点取文件顺序中的第一个和最后一个有效点。
- 数值超出 GPX 经纬度范围的点不计入统计。经纬度属性缺失或无法解析为数字时，程序会提示字段格式错误。完全没有有效点时，程序会提示检查轨迹结构。
- bbox 以 WGS84 十进制度输出，顺序为 `west`（最小经度）、`south`（最小纬度）、`east`（最大经度）、`north`（最大纬度）。经度直接取最小值和最大值，跨越 180° 经线的轨迹会得到较宽的框。 [GPX 1.1 格式说明](https://www.topografix.com/GPX/1/1/)
- 只要有一个有效轨迹点带有限数值的海拔，就显示“存在”。所有有效点都缺少海拔时显示“缺失”，仍会输出坐标摘要。
