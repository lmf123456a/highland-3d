# Highland 项目指南

## 产品方向

Highland 用徒步记录生成可旋转、可缩放的三维地形，让用户认出自己走过的路线和沿途山野。GPX 用于确定路线和取景范围，DEM 用于生成山形。有可用影像时，可以补充地表颜色。当天照片可以作为可选输入，用于标记记忆点和对照现场。照片可用 EXIF GPS 或拍摄时间与 GPX 匹配，并允许用户手动调整位置。

## 地形优化

- 现有 Python 流程已支持读取 GeoTIFF、将 GPX 贴合地形曲面、用 Plotly 导出离线 HTML。开始修改前先查看 `terrain.py` 和 `track_overlay.py`，以当前实现为准。
- 已观察到整张 DEM 在显示时缩到最长边 300 个采样点，并使用固定的 XYZ 显示比例。对已验证的图幅，采样间距达到数百米，山脊和沟谷的细节容易丢失，固定比例又放大了起伏。
- 优先验证按 GPX 范围裁剪并保留周边山脊、尽量保留 DEM 原始细节、将水平和垂直坐标统一为米、默认按真实比例显示。可以用现有 Python 流程先验证这一步。
- 选一段用户熟悉的路线，用同一份 GPX 和 DEM，在同一地点和朝向比较原预览、裁剪并校正比例后的预览、同一地形加影像的预览。重点检查山脊、沟谷和路线转折是否能认出来。这个对照目前待做。若高程源缺少细节，先确认源数据精度，再决定是否换数据。

## 可借鉴的开源项目

后续遇到对应功能时，优先查看下面的实现和文档，再结合 Highland 的现有代码选择可以复用的部分。

- **Ridgeline（MIT）**。参考按路线范围加余量、以米为单位设定目标采样密度、地形网格与贴图分开输出的做法。若需要更灵活的贴图或相机控制，再评估它的 Three.js 查看器。示例的高精度地形依赖意大利和法国的区域数据，Highland 可以从现有本地 Copernicus DEM 开始验证。[项目与效果图](https://github.com/fblln/ridgeline) · [Python 取景与采样代码](https://github.com/fblln/ridgeline/blob/main/tools/asset-baker/ridgeline_baker/pipeline.py#L672-L702)
- **Qgis2threejs（GPL-3.0）**。用同一份 DEM 和轨迹做独立的交互预览，比较不同取景范围、垂直比例、山体阴影和影像贴图的效果。[项目](https://github.com/minorua/Qgis2threejs) · [导出与贴图文档](https://minorua.github.io/Qgis2threejs/docs/2.10/Exporter.html)
- **GeoReel（GPL-3.0）**。参考 EXIF GPS 优先、拍摄时间补充的匹配流程，以及沿途照片的展示方式。[项目](https://github.com/elegos/georeel) · [照片匹配流程](https://github.com/elegos/georeel/blob/main/docs/ARCHITECTURE.md#2-photo-matcher-corephoto_matcherpy)

复用外部代码或影像时，分别核对代码许可和数据的使用、署名条件。个人 GPX 和当天照片可放在 Git 已忽略的 `data/private/` 中。
