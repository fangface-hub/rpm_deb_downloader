#!python3
"""RPM package service implementation."""
import os

import solv

from loggingex import generate_logger
from package_service import (PackageRequest, PackageService, ServiceRepo,
                             ServiceType)
from pathlibex import ensure_trailing_slash
from rpm_repository_client import RpmRepositoryClient
from rpm_resolver import RpmResolver

logger = generate_logger(name=__name__, debug=__debug__, filepath=__file__)


class RpmService(PackageService):
    """RPM package service implementation."""

    def __init__(self):
        super().__init__()
        self._repo_client = RpmRepositoryClient()
        self._resolver = RpmResolver()

    def resolve(
        self,
        repo_urls: list[ServiceRepo],
        package_names: list[PackageRequest],
        arch: str = "x86_64",
        probe: bool = False,
    ) -> list:
        """ServiceRepoリストからRPMリポジトリのみ有効なものを抽出し解決"""
        package_names = [
            item.package_name for item in package_names
            if item.service_type == ServiceType.RPM
        ]
        if not package_names:
            logger.info("[rpm] no RPM package requests; skipping")
            return []

        primary_xml_list = []
        for repo in repo_urls:
            if not repo.enable or repo.service_type != ServiceType.RPM:
                continue
            logger.info("[rpm] fetching repodata from %s", repo.repo_url)
            primary_xml = self._repo_client.fetch_repodata(repo.repo_url)
            primary_xml_list.append(
                (ensure_trailing_slash(repo.repo_url), primary_xml))

        pool = self._resolver.load_pool(primary_xml_list, arch=arch)
        repos = pool.repos() if callable(pool.repos) else pool.repos
        for repo in repos:
            logger.info("[rpm] repo %s solvables: %s", repo.name,
                        repo.nsolvables)
        if probe:
            results = self._resolver.find_solvables(pool, package_names)
            for name, entries in results.items():
                if not entries:
                    logger.info("[rpm] not found: %s", name)
                    continue
                for entry in entries:
                    logger.info("[rpm] found: %s %s %s @ %s", entry['name'],
                                entry['evr'], entry['arch'], entry['repo'])
                    for provide in entry.get("provides", []):
                        logger.info("[rpm] provides: %s", provide)
            return []

        resolved_objs = self._resolver.resolve(pool, package_names)
        # C拡張依存を排除したdictリストに変換
        resolved = []
        for pkg in resolved_objs:
            info = {
                "name": getattr(pkg, "name", None),
                "evr": getattr(pkg, "evr", None),
                "arch": getattr(pkg, "arch", None),
                "repo": getattr(getattr(pkg, "repo", None), "name", None),
                "location": None,
            }
            # location取得
            location = getattr(pkg, "location", None)
            if not location and hasattr(pkg, "lookup_location"):
                try:
                    location_value = pkg.lookup_location()
                except (AttributeError, TypeError):
                    location_value = None
                if isinstance(location_value, (list, tuple)):
                    if len(location_value) == 2 and all(
                            isinstance(value, str) for value in location_value):
                        location = "/".join(
                            value.strip("/") for value in location_value
                            if value)
                    else:
                        location = next((value for value in location_value
                                         if isinstance(value, str) and value),
                                        None)
                elif isinstance(location_value, str):
                    location = location_value
            if not location and hasattr(pkg, "lookup_str"):
                try:
                    location = pkg.lookup_str(solv.REPOSITORY_LOCATION)
                except (AttributeError, TypeError):
                    pass
            info["location"] = location
            resolved.append(info)
            logger.info("[rpm] resolved package: %s %s %s @ %s", info["name"],
                        info["evr"], info["arch"], info["repo"])
        return resolved

    def download(self,
                 resolved: list,
                 output_dir: str,
                 dry_run: bool = False) -> None:
        """Download resolved RPM packages to the specified output directory.

        Parameters
        ----------
        resolved : list
            List of resolved package objects.
        output_dir : str
            Directory to download the packages to.
        dry_run : bool, optional
            If True, do not perform actual download, by default False
        """
        logger.info("[rpm] preparing to download packages")
        missing_locations = 0
        for pkg in resolved:
            logger.info("[rpm] download package %s", pkg["name"])
            repo_url = ensure_trailing_slash(pkg["repo"])
            location = pkg["location"]
            if not location:
                missing_locations += 1
                if missing_locations <= 5:
                    logger.info("[rpm] missing location for %s", pkg["name"])
                continue
            url = repo_url + location
            dest = os.path.join(output_dir, os.path.basename(location))
            if dry_run:
                logger.info("[rpm] would download %s", url)
                continue
            logger.info("[rpm] downloading %s", url)
            self.download_with_resume(url, dest)

        if missing_locations:
            logger.info("[rpm] missing location total: %d", missing_locations)
