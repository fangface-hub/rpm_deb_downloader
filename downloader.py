#!python3
"""Downloader main entry point."""
# pylint: disable=W0718, C0103

import json
import os
import sys

import pathlibex
from deb_service import DebService
from loggingex import generate_logger, set_init_logfile
from package_service import PackageRequest, ServiceRepo, ServiceType


def _load_repos_from_json(filename, default):
    data_dir = pathlibex.get_data_dir()
    file_path = data_dir / filename
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return default


set_init_logfile()
logger = generate_logger(name=__name__, debug=__debug__, filepath=__file__)


def _is_git_lfs_pointer(file_path) -> bool:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return False
    return first_line == "version https://git-lfs.github.com/spec/v1"


def run(
    package_names,
    output_dir: str = "downloads",
    repos: list[ServiceRepo] = None,
    arch: str = "x86_64",
    dry_run: bool = False,
    rpm_probe: bool = False,
    package_requests: list[PackageRequest] = None,
) -> dict:
    """
    package_names : list
        List of target package names to resolve and download.
    output_dir : str, optional
        Directory to save downloaded packages (default is "downloads").
    repos : list[ServiceRepo], optional
        ServiceRepoのリスト。
    arch : str, optional
        Target architecture for RPM packages (default is "x86_64").
    dry_run : bool, optional
        If True, only resolve packages without downloading (default is False).
    rpm_probe : bool, optional
        If True, only probe for RPM package availability without downloading
        (default is False).
    """
    if package_requests is None:
        package_requests = []
        for package_name in package_names:
            package_requests.append(
                PackageRequest(service_type=ServiceType.RPM,
                               package_name=package_name))
            package_requests.append(
                PackageRequest(service_type=ServiceType.DEB,
                               package_name=package_name))

    rpm_package_names = [
        item.package_name for item in package_requests
        if item.service_type == ServiceType.RPM
    ]
    deb_package_names = [
        item.package_name for item in package_requests
        if item.service_type == ServiceType.DEB
    ]

    logger.info(
        ", ".join([
            "Starting download process", "rpm_packages: %s", "deb_packages: %s",
            "output_dir: %s", "arch: %s", "dry_run: %s", "rpm_probe: %s"
        ]), rpm_package_names, deb_package_names, output_dir, arch, dry_run,
        rpm_probe)
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    if rpm_package_names:
        try:
            from rpm_service import RpmService
        except ModuleNotFoundError as ex:
            if ex.name == "solv":
                app_dir = pathlibex.get_app_dir()
                candidate_paths = [
                    app_dir / "tools" / "bin",
                    app_dir / "_internal" / "tools" / "bin",
                ]
                for candidate in candidate_paths:
                    candidate_str = str(candidate)
                    if candidate.exists() and candidate_str not in sys.path:
                        sys.path.insert(0, candidate_str)
                try:
                    from rpm_service import RpmService
                except ModuleNotFoundError as second_ex:
                    if second_ex.name == "solv":
                        raise RuntimeError("RPM機能に必要な 'solv' モジュールが見つかりません。"
                                           " libsolvのWindowsビルド成果物"
                                           "（solv.py / solv.dll / solvext.dll）"
                                           "を同梱してください。") from second_ex
                    raise
                except SyntaxError as second_ex:
                    broken_candidates = [
                        candidate / "solv.py" for candidate in candidate_paths
                    ]
                    if any(file_path.exists() and _is_git_lfs_pointer(file_path)
                           for file_path in broken_candidates):
                        raise RuntimeError(
                            "RPM機能に必要な tools/bin/solv.py が Git LFS ポインタのままです。"
                            " 配布物作成時に Git LFS を有効化し、実体ファイルを同梱してください。"
                        ) from second_ex
                    raise
            else:
                raise
        except SyntaxError as ex:
            app_dir = pathlibex.get_app_dir()
            candidate_paths = [
                app_dir / "tools" / "bin" / "solv.py",
                app_dir / "_internal" / "tools" / "bin" / "solv.py",
            ]
            if any(path.exists() and _is_git_lfs_pointer(path)
                   for path in candidate_paths):
                raise RuntimeError(
                    "RPM機能に必要な tools/bin/solv.py が Git LFS ポインタのままです。"
                    " 配布物作成時に Git LFS を有効化し、実体ファイルを同梱してください。") from ex
            raise

        rpm_service = RpmService()
        resolved = rpm_service.resolve(repos, package_requests, arch, rpm_probe)
        if not rpm_probe:
            logger.info("Downloading RPM packages")
            rpm_service.download(resolved=resolved,
                                 output_dir=output_dir,
                                 dry_run=dry_run)
        results["rpm"] = resolved
    else:
        results["rpm"] = []
    deb_service = DebService()
    resolved = deb_service.resolve(repos, package_requests)
    logger.info("Downloading DEB packages")
    deb_service.download(resolved, output_dir, dry_run=dry_run)
    results["deb"] = resolved
    return results
