#!python3
"""RPM repository client."""
import gzip
import lzma
import xml.etree.ElementTree as ET

from http_client import HttpClient
from pathlibex import ensure_trailing_slash


class RpmRepositoryClient:
    """RPM repository client."""

    def __init__(self, http_client=None):
        self._http = http_client or HttpClient()

    def fetch_repodata(self, repo_url):
        """Fetch repodata from a given repository URL.

        Parameters
        ----------
        repo_url : str
            URL of the RPM repository

        Returns
        -------
        bytes
            Decompressed primary repodata XML content

        Raises
        ------
        RuntimeError
            If the primary metadata is not found in the repository
        """
        repo_url = ensure_trailing_slash(repo_url)
        repomd_url = repo_url + "repodata/repomd.xml"
        repomd_response = self._http.get(repomd_url)
        if (repomd_response.status_code == 404
                and repo_url.rstrip("/").endswith("/os")):
            fallback_url = repo_url[:-len("os/")]
            repomd_url = fallback_url + "repodata/repomd.xml"
            repomd_response = self._http.get(repomd_url)
            if repomd_response.ok:
                repo_url = fallback_url

        repomd = repomd_response.text
        root = ET.fromstring(repomd)

        primary_href = None
        for data in root.findall("{http://linux.duke.edu/metadata/repo}data"):
            if data.get("type") == "primary":
                primary_href = data.find(
                    "{http://linux.duke.edu/metadata/repo}location").get("href")
                break

        if not primary_href:
            raise RuntimeError(f"Primary metadata not found for {repo_url}")

        primary_url = repo_url + primary_href
        primary_blob = self._http.get(primary_url).content
        return self._decompress_primary(primary_href, primary_blob)

    def _decompress_primary(self, href, blob):
        """Decompress primary repodata based on file extension.

        Parameters
        ----------
        href : str
            The href of the primary repodata file

        blob : bytes
            Compressed primary repodata content

        Returns
        -------
        bytes
            Decompressed primary repodata content

        Raises
        ------
        RuntimeError
            If the repodata compression format is unsupported
        RuntimeError
            If the zstandard module is not installed but required
        """
        href = href.lower()
        if href.endswith(".gz"):
            return gzip.decompress(blob)
        if href.endswith(".xz"):
            return lzma.decompress(blob)
        if href.endswith(".zst"):
            try:
                import zstandard  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "zstandard is required to read .zst repodata") from exc
            return zstandard.ZstdDecompressor().decompress(blob)

        raise RuntimeError(f"Unsupported repodata compression: {href}")
