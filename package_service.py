#!python3
"""パッケージサービスの抽象基底クラスを定義するモジュール."""
import os
import sys
from abc import ABC, abstractmethod

from http_client import HttpClient
from loggingex import generate_logger

logger = generate_logger(name=__name__, debug=__debug__, filepath=__file__)


class PackageService(ABC):
    """パッケージサービスの抽象基底クラス (ダウンロード機能も提供)."""

    def __init__(self):
        self._http = HttpClient()

    @abstractmethod
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
        Returns
        -------
        list
            解決されたパッケージ情報のリスト."""
        logger.error("Not implemented: resolve")
        raise NotImplementedError

    @abstractmethod
    def download(self,
                 resolved: list,
                 output_dir: str,
                 dry_run: bool = False) -> None:
        """解決済みパッケージ情報から、実際にパッケージをダウンロードする.

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
        logger.error("Not implemented: download")
        raise NotImplementedError

    def download_with_resume(self,
                             url: str,
                             dest: str,
                             chunk_size: int = 1024 * 1024,
                             max_retries: int = 3) -> None:
        """ダウンロード再開機能付きダウンロード（堅牢化: リトライ・分割保存）.

        Parameters
        ----------
        url : str
            ダウンロード対象のURL.
        dest : str
            ダウンロードしたファイルの保存先パス.
        chunk_size : int, optional
            ダウンロードするチャンクのサイズ（バイト単位, default is 1MB).
        max_retries : int, optional
            ダウンロード失敗時の最大リトライ回数 (default is 3).

        Returns
        -------
        None
        """
        logger.debug("[package_service] downloading %s to %s", url, dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        attempt = 0
        while attempt < max_retries:
            headers = {}
            mode = "wb"
            existing = 0
            if os.path.exists(dest):
                existing = os.path.getsize(dest)
                if existing > 0:
                    headers["Range"] = f"bytes={existing}-"
                    mode = "ab"
            try:
                with self._http.get(
                        url,
                        stream=True,
                        headers=headers,
                ) as response:
                    if response.status_code == 416:
                        logger.info("[package_service] already complete: %s",
                                    dest)
                        return
                    response.raise_for_status()
                    with open(dest, mode) as handle:
                        for chunk in response.iter_content(
                                chunk_size=chunk_size):
                            if chunk:
                                handle.write(chunk)
                logger.info("[package_service] download succeeded: %s", dest)
                return
            except (OSError, AttributeError) as e:
                attempt += 1
                logger.warning(
                    "[package_service] download failed (attempt %d/%d): %s",
                    attempt, max_retries, e)
                sys.stderr.flush()
                if attempt >= max_retries:
                    logger.error(
                        "[package_service] download failed after %d attempts: "
                        "%s", max_retries, url)
                    sys.stderr.flush()
                    raise
                else:
                    logger.info("[package_service] retrying download: %s", url)
                    sys.stdout.flush()
            except ImportError as e:
                attempt += 1
                logger.warning(
                    "[package_service] download failed (attempt %d/%d): %s",
                    attempt, max_retries, e)
                sys.stderr.flush()
                if attempt >= max_retries:
                    logger.error(
                        "[package_service] download failed after %d attempts: "
                        "%s", max_retries, url)
                    sys.stderr.flush()
                    raise
                else:
                    logger.info("[package_service] retrying download: %s", url)
                    sys.stdout.flush()
