"""Unit tests for scripts/ensure_tectonic.py.

Network (urlretrieve), tarfile, and subprocess are mocked or use tmp_path
fixtures — no download or real binary execution happens.

  python3 -m pytest skills/report-builder/tests/
"""

import importlib.util
import io
import os
import stat
import tarfile
from pathlib import Path
from unittest import mock

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ensure_tectonic.py"
spec = importlib.util.spec_from_file_location("ensure_tectonic", SCRIPT)
et = importlib.util.module_from_spec(spec)
spec.loader.exec_module(et)


def _make_executable(path: Path) -> None:
    path.write_text("bin")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _make_archive(path: Path) -> None:
    with tarfile.open(path, "w:gz") as tar:
        data = b"#!/bin/sh\n"
        info = tarfile.TarInfo("tectonic")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def test_url_matches_pinned_version():
    assert et.TECTONIC_URL.startswith(
        "https://github.com/tectonic-typesetting/tectonic/releases/download/"
    )
    assert f"tectonic%40{et.TECTONIC_VERSION}" in et.TECTONIC_URL
    assert et.TECTONIC_URL.endswith(
        f"tectonic-{et.TECTONIC_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
    )


def test_paths_are_tmp_scoped():
    assert et.TECTONIC_ARCHIVE.startswith("/tmp/")
    assert et.TECTONIC_DIR.startswith("/tmp/")
    assert et.TECTONIC_PATH == os.path.join(et.TECTONIC_DIR, "tectonic")


def test_download_skips_when_binary_cached(tmp_path):
    exe = tmp_path / "tectonic"
    _make_executable(exe)
    with mock.patch.object(et.urllib.request, "urlretrieve") as dl:
        msg = et.download(archive=str(tmp_path / "a.tgz"), path=str(exe))
    dl.assert_not_called()
    assert "already cached" in msg


def test_download_fetches_when_missing(tmp_path):
    archive = tmp_path / "a.tgz"

    def fake_retrieve(url, dest):
        Path(dest).write_bytes(b"x" * 100)

    with mock.patch.object(et.urllib.request, "urlretrieve", side_effect=fake_retrieve) as dl:
        msg = et.download(archive=str(archive), path=str(tmp_path / "nope"))
    dl.assert_called_once()
    assert msg == "Downloaded: 100 bytes"


def test_extract_requires_archive(tmp_path):
    with pytest.raises(FileNotFoundError, match="download"):
        et.extract(
            archive=str(tmp_path / "missing.tgz"),
            directory=str(tmp_path / "d"),
            path=str(tmp_path / "d" / "tectonic"),
        )


def test_extract_makes_executable_and_cleans_up(tmp_path):
    archive = tmp_path / "a.tgz"
    _make_archive(archive)
    dest = tmp_path / "d"
    msg = et.extract(archive=str(archive), directory=str(dest), path=str(dest / "tectonic"))
    assert os.access(dest / "tectonic", os.X_OK)
    assert not archive.exists()
    assert "Extracted" in msg


def test_extract_skips_when_already_extracted(tmp_path):
    exe = tmp_path / "d" / "tectonic"
    exe.parent.mkdir()
    _make_executable(exe)
    msg = et.extract(
        archive=str(tmp_path / "missing.tgz"), directory=str(exe.parent), path=str(exe)
    )
    assert "already extracted" in msg


def test_verify_requires_binary(tmp_path):
    with pytest.raises(FileNotFoundError, match="download"):
        et.verify(path=str(tmp_path / "nope"))


def test_verify_returns_version_string(tmp_path):
    exe = tmp_path / "tectonic"
    _make_executable(exe)
    with mock.patch.object(et.subprocess, "run") as run:
        run.return_value = mock.Mock(stdout="tectonic 0.15.0\n", stderr="")
        assert et.verify(path=str(exe)) == "tectonic 0.15.0"
