#!python3
"""RPM package resolver implementation."""
import atexit
import gc
import os
import shutil
import subprocess
import tempfile

import solv


class RpmResolver:
    """RPM package resolver implementation."""

    def __init__(self):
        self._temp_paths = []
        atexit.register(self._cleanup_temp_paths)

    def _cleanup_temp_paths(self):
        for path in self._temp_paths:
            try:
                os.remove(path)
            except OSError:
                pass

    def _add_rpmmd_repo(self, repo: solv.Repo, primary_xml: bytes) -> None:
        """Add RPM metadata to the given repository.

        Parameters
        ----------
        repo : solv.Repo
            RPM repository object.
        primary_xml : bytes
            RPM repository primary XML metadata.
        """
        if (hasattr(repo, "add_rpmmd") and hasattr(solv, "xfopen")
                and hasattr(solv, "Repo_add_rpmmd")):
            with tempfile.NamedTemporaryFile(delete=False) as handle:
                handle.write(primary_xml)
                temp_path = handle.name
            try:
                fp = solv.xfopen(temp_path, "r")
                repo.add_rpmmd(fp, None)
                del fp
                gc.collect()
                self._temp_paths.append(temp_path)
                return
            except (AttributeError, TypeError, RuntimeError):
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        repo2solv = shutil.which("repo2solv")
        rpmmd2solv = shutil.which("rpmmd2solv")
        if not repo2solv:
            local_repo2solv = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "tools",
                "bin",
                "repo2solv.exe",
            )
            if os.path.exists(local_repo2solv):
                repo2solv = local_repo2solv
        if not rpmmd2solv:
            local_rpmmd2solv = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "tools",
                "bin",
                "rpmmd2solv.exe",
            )
            if os.path.exists(local_rpmmd2solv):
                rpmmd2solv = local_rpmmd2solv
        if not repo2solv and not rpmmd2solv:
            raise RuntimeError(
                "repo.add_rpmmd is not available; repo2solv or rpmmd2solv is "
                "required in PATH or tools/bin")

        with tempfile.TemporaryDirectory() as temp_dir:
            primary_path = os.path.join(temp_dir, "primary.xml")
            solv_path = os.path.join(temp_dir, "primary.solv")
            with open(primary_path, "wb") as handle:
                handle.write(primary_xml)

            if repo2solv:
                result = subprocess.run(
                    [repo2solv, "-o", solv_path, primary_path],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        "repo2solv failed: "
                        f"{result.stdout.strip()} {result.stderr.strip()}")

                self._add_solv_file(repo, solv_path, "repo2solv")
            else:
                result = subprocess.run(
                    [rpmmd2solv],
                    input=primary_xml,
                    capture_output=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError("rpmmd2solv failed: "
                                       f"{result.stdout.decode().strip()} "
                                       f"{result.stderr.decode().strip()}")
                if os.getenv("RPM_DEBUG") == "1":
                    print("[rpm] rpmmd2solv output bytes: "
                          f"{len(result.stdout)}")
                with tempfile.NamedTemporaryFile(delete=False) as handle:
                    handle.write(result.stdout)
                    solv_temp_path = handle.name
                try:
                    self._add_solv_file(repo, solv_temp_path, "rpmmd2solv")
                finally:
                    if os.path.exists(solv_temp_path):
                        if os.name == "nt":
                            self._temp_paths.append(solv_temp_path)
                        else:
                            os.remove(solv_temp_path)

    def load_pool(self, primary_xml_list: list, arch: str = None) -> solv.Pool:
        """Load RPM package pool from primary XML metadata.

        Parameters
        ----------
        primary_xml_list : list
            List of tuples (repo_name, primary_xml_bytes).
        arch : str, optional
            Target architecture, by default None

        Returns
        -------
        solv.Pool
            RPM package pool object.
        """
        pool = solv.Pool()
        if hasattr(pool, "setdisttype") and hasattr(solv, "DISTTYPE_RPM"):
            pool.setdisttype(solv.DISTTYPE_RPM)
        if arch and hasattr(pool, "setarch"):
            pool.setarch(arch)

        for name, primary_xml in primary_xml_list:
            repo = pool.add_repo(name)
            self._add_rpmmd_repo(repo, primary_xml)

        if hasattr(pool, "create_whatprovides"):
            pool.create_whatprovides()
        else:
            pool.createwhatprovides()
        return pool

    def resolve(self, pool: solv.Pool, package_names: list) -> list:
        """Resolve RPM packages from the pool.

        Parameters
        ----------
        pool : solv.Pool
            RPM package pool object.
        package_names : list
            List of package names to resolve.

        Returns
        -------
        list
            List of resolved package objects.
        """
        jobs = []
        for name in package_names:
            selection = pool.select(name, solv.Selection.SELECTION_NAME)
            if not selection or selection.isempty():
                raise RuntimeError(f"RPM package not found: {name}")
            if hasattr(selection, "jobs"):
                jobs.extend(selection.jobs(solv.Job.SOLVER_INSTALL))
            elif hasattr(pool, "Job"):
                jobs.append(pool.Job(solv.Job.SOLVER_INSTALL, selection))
            else:
                jobs.append(solv.Job(pool, solv.Job.SOLVER_INSTALL, selection))

        solver = pool.Solver()
        if hasattr(solver, "set_flag") and hasattr(solver,
                                                   "SOLVER_FLAG_SPLITPROVIDES"):
            solver.set_flag(solver.SOLVER_FLAG_SPLITPROVIDES, True)
        problems = solver.solve(jobs)
        if problems:
            details = "; ".join(str(problem) for problem in problems)
            debug_info = self._format_debug_info(pool)
            if debug_info:
                details = f"{details} | {debug_info}"
            raise RuntimeError(f"RPM dependency solve failed: {details}")

        transaction = solver.transaction()
        if hasattr(transaction, "newpackages"):
            return list(transaction.newpackages())
        return list(transaction.newsolvables())

    def find_solvables(self, pool: solv.Pool, package_names: list) -> dict:
        """Find solvable RPM packages in the pool.

        Parameters
        ----------
        pool : solv.Pool
            RPM package pool object.
        package_names : list
            List of package names to find solvables for.

        Returns
        -------
        dict
            Dictionary mapping package names to lists of solvable entries.
        """
        results = {}
        for name in package_names:
            selection = pool.select(name, solv.Selection.SELECTION_NAME)
            if not selection or selection.isempty():
                selection = pool.select(name, solv.Selection.SELECTION_PROVIDES)
            if not selection or selection.isempty():
                results[name] = []
                continue
            entries = []
            for solvable in selection.solvables():
                repo = getattr(getattr(solvable, "repo", None), "name", None)
                provides = []
                pool_ref = getattr(solvable, "pool", None)
                if not pool_ref:
                    repo_ref = getattr(solvable, "repo", None)
                    pool_ref = getattr(repo_ref, "pool", None)
                if pool_ref and hasattr(solvable, "lookup_deparray"):
                    dep_ids = solvable.lookup_deparray(solv.SOLVABLE_PROVIDES)
                    if dep_ids:
                        provides = [
                            self._dep_to_str(pool_ref, dep_id)
                            for dep_id in dep_ids
                        ]
                provides_match = [value for value in provides if name in value]
                entries.append({
                    "name": getattr(solvable, "name", None),
                    "evr": getattr(solvable, "evr", None),
                    "arch": getattr(solvable, "arch", None),
                    "repo": repo,
                    "provides": provides_match,
                })
            results[name] = entries
        return results

    @staticmethod
    def _dep_to_str(pool: solv.Pool, dep_id: int) -> str:
        """Convert a dependency ID to its string representation.

        Parameters
        ----------
        pool : solv.Pool
            RPM package pool object.
        dep_id : int
            Dependency ID to convert.

        Returns
        -------
        str
            String representation of the dependency ID.
        """
        try:
            return pool.dep2str(dep_id)
        except (TypeError, ValueError):
            return str(dep_id)

    def _add_solv_file(self, repo: solv.Repo, solv_path: str,
                       source: str) -> None:
        """Add a solv file to the repository.

        Parameters
        ----------
        repo : solv.Repo
            RPM package repository object.
        solv_path : str
            Path to the solv file.
        source : str
            Source description for error reporting.
        """
        if hasattr(solv, "xfopen"):
            fp = None
            try:
                mode = "rb" if os.name == "nt" else "r"
                fp = solv.xfopen(solv_path, mode)
                repo.add_solv(fp, 0)
            finally:
                if fp is not None:
                    del fp
                    gc.collect()
        else:
            repo.add_solv(solv_path, 0)

        if hasattr(repo, "internalize"):
            repo.internalize()
        if getattr(repo, "nsolvables", 0) == 0:
            pool_ref = getattr(repo, "pool", None)
            err = self._pool_errstr(pool_ref)
            raise RuntimeError(f"{source} produced no solvables: {err}")

    @staticmethod
    def _pool_errstr(pool_ref: solv.Pool) -> str:
        """Get the error string from the pool reference.

        Parameters
        ----------
        pool_ref : solv.Pool
            RPM package pool object.

        Returns
        -------
        str
            Error string from the pool reference.
        """
        if not pool_ref:
            return "unknown error"
        err = getattr(pool_ref, "errstr", None)
        if callable(err):
            return err()
        if err:
            return err
        return "unknown error"

    def _format_debug_info(self, pool: solv.Pool) -> str:
        """Format debug information for the given pool.

        Parameters
        ----------
        pool : solv.Pool
            RPM package pool object.

        Returns
        -------
        str
            Formatted debug information string.
        """
        queries = [
            "glibc-gconv-extra(x86-64)",
            "glibc-gconv-extra",
            "redhat-rpm-config",
        ]
        parts = []
        for query in queries:
            matches = self._collect_provides(pool, query)
            if not matches:
                parts.append(f"debug {query}: 0 providers")
                continue
            summary = ", ".join(
                f"{item['name']}-{item['evr']}.{item['arch']}@{item['repo']}"
                for item in matches[:5])
            parts.append(f"debug {query}: {len(matches)} providers: {summary}")
        return " | ".join(parts)

    def _collect_provides(self, pool: solv.Pool, query: str) -> list[dict]:
        """Collect provides information for a given query.

        Parameters
        ----------
        pool : solv.Pool
            RPM package pool object.
        query : str
            Query string to search for.

        Returns
        -------
        list[dict]
            List of dictionaries containing provides information.
        """
        selection = pool.select(query, solv.Selection.SELECTION_PROVIDES)
        if not selection:
            selection = pool.select(query, solv.Selection.SELECTION_NAME)
        if not selection:
            return []
        results = []
        for solvable in selection.solvables():
            repo = getattr(getattr(solvable, "repo", None), "name", None)
            results.append({
                "name": getattr(solvable, "name", None),
                "evr": getattr(solvable, "evr", None),
                "arch": getattr(solvable, "arch", None),
                "repo": repo,
            })
        return results
