#!python3
"""Debian package metadata parser."""
from pathlibex import ensure_trailing_slash


class DebMetadataParser:
    """Debian package metadata parser."""

    @staticmethod
    def parse_control_paragraphs(text: str) -> dict:
        """Parse control paragraphs from Debian package metadata.

        Parameters
        ----------
        text : str
            The control file content.

        Returns
        ------
        dict
            A dictionary representing a control paragraph.
        """
        paragraph = {}
        current_key = None

        for line in text.splitlines():
            if not line.strip():
                if paragraph:
                    yield paragraph
                    paragraph = {}
                    current_key = None
                continue

            if line[0].isspace() and current_key:
                paragraph[current_key] += " " + line.strip()
                continue

            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            current_key = key.strip()
            paragraph[current_key] = value.strip()

        if paragraph:
            yield paragraph

    @staticmethod
    def parse_depends(depends_field: str) -> list:
        """Parse the Depends field from a control paragraph.

        Parameters
        ----------
        depends_field : str
            The raw Depends field value from the control paragraph.
        Returns
        -------
        list
            A list of package names that are dependencies.
        """

        if not depends_field:
            return []

        deps = []
        for entry in depends_field.split(","):
            entry = entry.strip()
            if not entry:
                continue
            first_alt = entry.split("|")[0].strip()
            name = first_alt.split(" ")[0].strip()
            if name:
                deps.append(name)
        return deps

    @staticmethod
    def repo_base_url(repo_url: str) -> str:
        """Get the base URL of a Debian repository.

        Parameters
        ----------
        repo_url : str
            The full URL of the Debian repository.

        Returns
        -------
        str
            The base URL of the repository.
        """
        marker = "/dists/"
        index = repo_url.find(marker)
        if index == -1:
            return ensure_trailing_slash(repo_url)
        return ensure_trailing_slash(repo_url[:index])
