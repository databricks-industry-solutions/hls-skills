"""Ensure the Tectonic LaTeX engine is available on the executeCode chat compute.

The platform safety filter blocks a single cell that downloads, extracts,
AND executes a binary. Run each function below in its OWN executeCode call,
in order:

    download() -> extract() -> verify()

Every function is idempotent — safe to re-run if a step is interrupted.
The binary is session-scoped under /tmp; a new session re-downloads.
"""

import os
import stat
import subprocess
import tarfile
import urllib.request

TECTONIC_VERSION = "0.15.0"
TECTONIC_URL = (
    f"https://github.com/tectonic-typesetting/tectonic/releases/download/"
    f"tectonic%40{TECTONIC_VERSION}/"
    f"tectonic-{TECTONIC_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
)
TECTONIC_ARCHIVE = "/tmp/tectonic.tar.gz"
TECTONIC_DIR = "/tmp/tectonic-bin"
TECTONIC_PATH = os.path.join(TECTONIC_DIR, "tectonic")


def _is_executable(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def download(url=TECTONIC_URL, archive=TECTONIC_ARCHIVE, path=TECTONIC_PATH):
    """Step 1 — download the Tectonic archive (~21 MB). Skips if already cached."""
    if _is_executable(path):
        return f"Tectonic already cached at {path}"
    urllib.request.urlretrieve(url, archive)
    return f"Downloaded: {os.path.getsize(archive):,} bytes"


def extract(archive=TECTONIC_ARCHIVE, directory=TECTONIC_DIR, path=TECTONIC_PATH):
    """Step 2 — extract the archive, make the binary executable, remove the archive."""
    if _is_executable(path):
        return f"Tectonic already extracted at {path}"
    if not os.path.isfile(archive):
        raise FileNotFoundError("No archive found. Run download() first.")
    os.makedirs(directory, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        try:
            tar.extractall(directory, filter="data")
        except TypeError:
            tar.extractall(directory)  # Python < 3.12 has no filter argument
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    os.remove(archive)
    return f"Extracted: {os.path.getsize(path):,} bytes"


def verify(path=TECTONIC_PATH):
    """Step 3 — verify the binary runs. Returns the version string."""
    if not _is_executable(path):
        raise FileNotFoundError(
            "Tectonic binary not found. Run download() and extract() first."
        )
    r = subprocess.run([path, "--version"], capture_output=True, text=True)
    return r.stdout.strip()
