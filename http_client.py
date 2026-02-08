#!python3
"""HTTP client with retry mechanism."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class HttpClient:
    """HTTP client with retry mechanism."""

    def __init__(
        self,
        session=None,
        timeout=60,
        retries=3,
        backoff=0.5,
        status_forcelist=None,
    ):
        self._session = session or requests.Session()
        self._timeout = timeout

        if status_forcelist is None:
            status_forcelist = [429, 500, 502, 503, 504]

        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=backoff,
            status_forcelist=status_forcelist,
            allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def get(self,
            url: str,
            stream: bool = False,
            headers: dict = None) -> requests.Response:
        """assign GET request with retry mechanism.

        Parameters
        ----------
        url : str
            url to GET
        stream : bool, optional
            stream the response content, by default False
        headers : dict, optional
            headers to include in the request, by default None

        Returns
        -------
        requests.Response
            Response object
        """
        return self._session.get(
            url,
            stream=stream,
            headers=headers,
            timeout=self._timeout,
        )
