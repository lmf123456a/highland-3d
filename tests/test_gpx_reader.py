from pathlib import Path

import pytest

from gpx_reader import GPXReadError, read_gpx_segments, summarize_track
from main import main


DEMO_GPX = Path(__file__).resolve().parents[1] / "samples" / "demo.gpx"


def write_gpx(tmp_path: Path, contents: str) -> Path:
    path = tmp_path / "test.gpx"
    path.write_text(contents, encoding="utf-8")
    return path


def test_demo_summary() -> None:
    summary = summarize_track(read_gpx_segments(DEMO_GPX))

    assert summary.point_count == 4
    assert summary.segment_count == 2
    assert (summary.start.latitude, summary.start.longitude) == (30.100, 100.200)
    assert (summary.end.latitude, summary.end.longitude) == (30.102, 100.204)
    assert summary.bbox == {
        "west": 100.195,
        "south": 30.099,
        "east": 100.211,
        "north": 30.104,
    }
    assert summary.has_elevation is True


def test_segments_keep_order_across_tracks(tmp_path: Path) -> None:
    path = write_gpx(
        tmp_path,
        """<gpx version="1.1" creator="test">
        <trk>
          <trkseg><trkpt lat="1" lon="2" /></trkseg>
          <trkseg />
          <trkseg><trkpt lat="3" lon="4" /></trkseg>
        </trk>
        <trk><trkseg><trkpt lat="5" lon="6" /></trkseg></trk>
        </gpx>""",
    )

    segments = read_gpx_segments(path)

    assert [[point.latitude for point in segment] for segment in segments] == [
        [1], [], [3], [5]
    ]
    assert summarize_track(segments).segment_count == 4


def test_missing_elevation(tmp_path: Path) -> None:
    path = write_gpx(
        tmp_path, '<gpx><trk><trkseg><trkpt lat="1" lon="2" /></trkseg></trk></gpx>'
    )

    summary = summarize_track(read_gpx_segments(path))

    assert summary.point_count == 1
    assert summary.has_elevation is False


def test_only_valid_points_count(tmp_path: Path) -> None:
    path = write_gpx(
        tmp_path,
        """<gpx><trk><trkseg>
        <trkpt lat="91" lon="2"><ele>100</ele></trkpt>
        <trkpt lat="1" lon="180" />
        <trkpt lat="nan" lon="2" />
        <trkpt lat="1" lon="-180"><ele>0</ele></trkpt>
        </trkseg></trk></gpx>""",
    )

    summary = summarize_track(read_gpx_segments(path))

    assert summary.point_count == 1
    assert summary.start.longitude == -180
    assert summary.has_elevation is True


@pytest.mark.parametrize(
    "contents",
    [
        '<gpx><trk><trkseg /></trk></gpx>',
        '<gpx><rte><rtept lat="1" lon="2" /></rte></gpx>',
        '<gpx><trk><trkseg><trkpt lat="-91" lon="2" /></trkseg></trk></gpx>',
    ],
    ids=["empty-segment", "route-only", "all-points-invalid"],
)
def test_no_valid_track_points(tmp_path: Path, contents: str) -> None:
    path = write_gpx(tmp_path, contents)

    with pytest.raises(GPXReadError, match="没有有效轨迹点"):
        summarize_track(read_gpx_segments(path))


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "文件为空"),
        (" \n\t", "文件为空"),
        ("<gpx><trk></gpx>", "XML 格式错误"),
        ("<other><trk><trkseg /></trk></other>", "根元素应为 gpx"),
        ('<gpx><trk><trkseg><trkpt lat="abc" lon="2" /></trkseg></trk></gpx>', "字段格式错误"),
        ('<gpx><trk><trkseg><trkpt lon="2" /></trkseg></trk></gpx>', "字段格式错误"),
    ],
    ids=["empty-file", "whitespace", "broken-xml", "wrong-root", "non-numeric", "missing-latitude"],
)
def test_invalid_input(tmp_path: Path, contents: str, message: str) -> None:
    path = write_gpx(tmp_path, contents)

    with pytest.raises(GPXReadError, match=message):
        read_gpx_segments(path)


def test_cli_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--gpx", str(DEMO_GPX)]) == 0
    captured = capsys.readouterr()

    assert captured.out.splitlines() == [
        "轨迹点数：4",
        "轨迹段数：2",
        "起点：latitude=30.1, longitude=100.2",
        "终点：latitude=30.102, longitude=100.204",
        "bbox (WGS84，度)：",
        "  west=100.195",
        "  south=30.099",
        "  east=100.211",
        "  north=30.104",
        "海拔数据：存在",
    ]
    assert captured.err == ""


def test_cli_reports_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "missing.gpx"

    assert main(["--gpx", str(path)]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert f"错误：文件不存在：{path}" in captured.err
