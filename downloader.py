#!python3
"""Downloader main entry point."""
# pylint: disable=W0718, C0103

import argparse
import json
import os
import sys
import traceback

import pathlibex
from deb_service import DebService
from loggingex import generate_logger, set_init_logfile
from rpm_service import RpmService


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


DEFAULT_RPM_REPOS = _load_repos_from_json(
    os.path.join("tools", "DEFAULT_RPM_REPOS.json"), [
        "https://dl.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/",
        "https://dl.rockylinux.org/pub/rocky/9/AppStream/x86_64/os/",
        "https://dl.rockylinux.org/pub/rocky/9/CRB/x86_64/os/",
        "https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/"
    ])

DEFAULT_DEB_REPOS = _load_repos_from_json(
    os.path.join("tools", "DEFAULT_DEB_REPOS.json"), [
        "http://ftp.jp.debian.org/debian/dists/bullseye/main/binary-amd64/",
        "http://ftp.jp.debian.org/debian/dists/bullseye/contrib/binary-amd64/"
    ])

set_init_logfile()
logger = generate_logger(name=__name__, debug=__debug__, filepath=__file__)


def run(
    package_names,
    output_dir: str = "downloads",
    rpm_repos: list = None,
    deb_repos: list = None,
    arch: str = "x86_64",
    use_rpm: bool = True,
    use_deb: bool = True,
    dry_run: bool = False,
    rpm_probe: bool = False,
) -> dict:
    """run the package resolution and download process.

    Parameters
    ----------
    package_names : list
        List of target package names to resolve and download.
    output_dir : str, optional
        Directory to save downloaded packages (default is "downloads").
    rpm_repos : list, optional
        List of RPM repository URLs to use for resolution (default is None,
          which uses DEFAULT_RPM_REPOS).
    deb_repos : list, optional
        List of DEB repository URLs to use for resolution (default is None,
          which uses DEFAULT_DEB_REPOS).
    arch : str, optional
        Target architecture for RPM packages (default is "x86_64").
    use_rpm : bool, optional
        Whether to process RPM packages (default is True).
    use_deb : bool, optional
        Whether to process DEB packages (default is True).
    dry_run : bool, optional
        If True, only resolve packages without downloading (default is False).
    rpm_probe : bool, optional
        If True, only probe for RPM package availability without downloading
          (default is False).
    Returns
    -------
    dict
        A dictionary containing resolved package information for
          RPM and DEB packages.
    """
    logger.info(
        ", ".join([
            "Starting download process for packages: %s", "output_dir: %s",
            "rpm_probe: %s", "deb_repos: %s", "arch: %s", "use_rpm: %s",
            "use_deb: %s", "dry_run: %s", "rpm_probe: %s"
        ]), package_names, output_dir, rpm_probe, deb_repos, arch, use_rpm,
        use_deb, dry_run, rpm_probe)
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    if use_rpm:
        rpm_service = RpmService()
        resolved = rpm_service.resolve(repo_urls=rpm_repos,
                                       package_names=package_names,
                                       arch=arch,
                                       probe=rpm_probe)
        if not rpm_probe:
            logger.info("Downloading RPM packages")
            rpm_service.download(resolved=resolved,
                                 output_dir=output_dir,
                                 dry_run=dry_run)
        results["rpm"] = resolved
    if use_deb:
        deb_service = DebService()
        resolved = deb_service.resolve(deb_repos, package_names)
        logger.info("Downloading DEB packages")
        deb_service.download(resolved, output_dir, dry_run=dry_run)
        results["deb"] = resolved
    return results


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Resolve and download RPM/DEB packages from multiple repos."
    )
    parser.add_argument("packages", nargs="+", help="Target package names")
    parser.add_argument("--out", default="downloads", help="Output directory")
    parser.add_argument(
        "--rpm-repo",
        action="append",
        default=[],
        help="RPM repo URL",
    )
    parser.add_argument(
        "--deb-repo",
        action="append",
        default=[],
        help="DEB repo URL",
    )
    parser.add_argument("--arch", default="x86_64", help="RPM architecture")
    parser.add_argument(
        "--no-rpm",
        action="store_true",
        help="Skip RPM processing",
    )
    parser.add_argument(
        "--no-deb",
        action="store_true",
        help="Skip DEB processing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve only, no downloads",
    )
    parser.add_argument(
        "--rpm-probe",
        action="store_true",
        help="Print RPM package availability and exit",
    )
    return parser.parse_args()


def main():
    """Main entry point for the downloader script."""
    args = parse_args()
    rpm_repos = args.rpm_repo or DEFAULT_RPM_REPOS
    deb_repos = args.deb_repo or DEFAULT_DEB_REPOS

    run(
        package_names=args.packages,
        output_dir=args.out,
        rpm_repos=rpm_repos,
        deb_repos=deb_repos,
        arch=args.arch,
        use_rpm=not args.no_rpm,
        use_deb=not args.no_deb,
        dry_run=args.dry_run,
        rpm_probe=args.rpm_probe,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        traceback_str = traceback.format_exc()

        print(f"Exception: {exc}", file=sys.stderr)
        print(traceback_str, file=sys.stderr)
        logger.fatal("Exception: %s\n%s", exc, traceback_str)
        sys.exit(1)
