#!python3
"""Debian package service implementation."""
import os

from deb_metadata_parser import DebMetadataParser
from deb_repository_client import DebRepositoryClient
from loggingex import generate_logger
from package_service import PackageService
from pathlibex import ensure_trailing_slash

logger = generate_logger(name=__name__, debug=__debug__, filepath=__file__)


class DebService(PackageService):
    """debパッケージサービスの実装クラス. """

    def __init__(self):
        super().__init__()
        self._repo_client = DebRepositoryClient()
        self._parser = DebMetadataParser()

    def resolve(self, repo_urls: list, package_names: list) -> list:
        """リポジトリURLとパッケージ名から、ダウンロード対象のパッケージ情報を解決する.

        Parameters
        ----------
        repo_urls : list
            リポジトリのベースURLのリスト.
        package_names : list
            解決対象のパッケージ名のリスト.
        Returns
        -------
        list
            解決されたパッケージ情報のリスト.
        Raises
        ------
        NotImplementedError
            サブクラスで実装されていない場合に発生.
        """

        packages = self._collect_metadata(repo_urls)
        required = self._resolve_dependencies(package_names, packages)
        # パッケージ情報のdictリストに変換
        resolved = []
        for name in sorted(required):
            meta = packages.get(name)
            if meta:
                info = {"name": name}
                info.update(meta)
                resolved.append(info)
        return resolved

    def download(self,
                 resolved: list,
                 output_dir: str,
                 dry_run: bool = False) -> None:
        """ 解決済みパッケージ情報から、実際にパッケージをダウンロードする.
        Parameters
        ----------
        resolved : list
            resolve()で解決されたパッケージ情報のリスト.
        output_dir : str
            ダウンロードしたパッケージを保存するディレクトリ.
        dry_run : bool, optional
            Trueの場合、実際のダウンロードは行わず、ダウンロード対象
            のURLと保存先をログに出力する (default is False).
        Returns
        -------
        None
        """

        for meta in resolved:
            name = meta.get("name")
            filename = meta.get("filename")
            if not filename:
                logger.info("[deb] missing filename for %s", name)
                continue
            url = meta["base_url"] + filename
            dest = os.path.join(output_dir, os.path.basename(filename))
            if dry_run:
                logger.info("[deb] would download %s", url)
                continue
            logger.info("[deb] downloading %s", url)
            self.download_with_resume(url, dest)

    def _collect_metadata(self, repo_urls: list) -> dict:
        """リポジトリURLのリストから、パッケージ名をキーとするパッケージ情報の辞書を収集する.

        Parameters
        ----------
        repo_urls : list
            リポジトリのベースURLのリスト.
        Returns
        -------
        dict
            パッケージ名をキーとするパッケージ情報の辞書.
        """

        packages = {}
        for repo_url in repo_urls:
            repo_url = ensure_trailing_slash(repo_url)
            base_url = self._parser.repo_base_url(repo_url)
            packages_data = self._repo_client.fetch_packages(repo_url)
            for paragraph in self._parser.parse_control_paragraphs(
                    packages_data):
                name = paragraph.get("Package")
                if not name or name in packages:
                    continue
                packages[name] = {
                    "depends":
                    self._parser.parse_depends(paragraph.get("Depends")),
                    "filename": paragraph.get("Filename"),
                    "base_url": base_url,
                }
        return packages

    def _resolve_dependencies(self, package_names: list, packages: dict) -> set:
        """パッケージ名のリストから、依存関係を解決して必要なパッケージ名のセットを返す.

        Parameters
        ----------
        package_names : list
            解決対象のパッケージ名のリスト.
        packages : dict
            パッケージ名をキーとするパッケージ情報の辞書.
        Returns
        -------
        set
            解決された必要なパッケージ名のセット.
        """
        required = set()
        queue = list(package_names)

        while queue:
            name = queue.pop(0)
            if name in required:
                continue
            required.add(name)

            meta = packages.get(name)
            if not meta:
                continue
            for dep in meta["depends"]:
                if dep not in required:
                    queue.append(dep)

        return required
