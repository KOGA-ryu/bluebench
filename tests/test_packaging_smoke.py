from __future__ import annotations

import importlib.metadata
import importlib.util
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackagingSmokeTests(unittest.TestCase):
    def test_editable_install_exposes_bluebench_console_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            venv_path = Path(tmp_dir) / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            python_bin = venv_path / "bin" / "python"
            bluebench_bin = venv_path / "bin" / "bluebench"
            _seed_local_setuptools(venv_path)
            subprocess.run(
                [str(python_bin), "-m", "pip", "install", "-e", ".", "--no-deps", "--no-build-isolation"],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [str(bluebench_bin), "--version"],
                cwd=str(REPO_ROOT),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "0.1.0")


def _seed_local_setuptools(venv_path: Path) -> None:
    spec = importlib.util.find_spec("setuptools")
    if spec is None or spec.origin is None:
        raise unittest.SkipTest("host setuptools is unavailable; offline editable-install smoke test cannot run")
    setuptools_root = Path(spec.origin).resolve().parent
    venv_site_packages = next((venv_path / "lib").glob("python*/site-packages"))
    target_pkg = venv_site_packages / "setuptools"
    if not target_pkg.exists():
        shutil.copytree(setuptools_root, target_pkg)

    distribution = importlib.metadata.distribution("setuptools")
    dist_info_src = Path(distribution._path)  # type: ignore[attr-defined]
    target_dist_info = venv_site_packages / dist_info_src.name
    if not target_dist_info.exists():
        shutil.copytree(dist_info_src, target_dist_info)


if __name__ == "__main__":
    unittest.main()
