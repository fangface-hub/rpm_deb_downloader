import gzip
import io

from http_client import HttpClient
from pathlibex import ensure_trailing_slash


class DebRepositoryClient:

    def __init__(self, http_client=None):
        self._http = http_client or HttpClient()

    def fetch_packages(self, repo_url):
        repo_url = ensure_trailing_slash(repo_url)
        packages_url = repo_url + "Packages.gz"
        response = self._http.get(packages_url)
        response.raise_for_status()
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as handle:
            return handle.read().decode("utf-8", errors="replace")
