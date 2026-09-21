"""Select CI jobs conservatively; unknown paths and non-PR events run all jobs."""

import os
import subprocess
from pathlib import Path

ALL_JOBS = frozenset({"python", "web", "e2e", "docs"})


def select_jobs(paths: list[str]) -> frozenset[str]:
    if not paths:
        return ALL_JOBS
    selected: set[str] = set()
    for path in paths:
        # These reference documents are loaded by the Python runtime.
        if path.startswith(
            ("api/", "src/", "tests/", "validation/", "docs/ips_reference/")
        ):
            selected.update({"python", "e2e"})
        elif path in {"AGENTS.md", "web/AGENTS.md", "web/README.md"} or (
            "/" not in path and path.startswith("README") and path.endswith(".md")
        ):
            continue
        elif path.startswith("guide/") or path == "mkdocs.yml":
            selected.add("docs")
        elif path.startswith("docs/"):
            continue
        elif path.startswith("web/"):
            selected.update({"web", "e2e"})
        else:
            # Includes workflow/tooling changes, root dependencies and new directories.
            return ALL_JOBS
    return frozenset(selected)


def changed_paths(base: str, head: str) -> list[str]:
    # NUL delimiters preserve whitespace; disabling rename detection includes both
    # ends of a move, including a runtime file moved into a documentation directory.
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", "--no-renames", f"{base}...{head}"],
        check=True,
        capture_output=True,
    )
    return os.fsdecode(result.stdout).rstrip("\0").split("\0") if result.stdout else []


def event_jobs(event: str, base: str, head: str) -> frozenset[str]:
    if event != "pull_request" or not base or not head:
        return ALL_JOBS
    try:
        return select_jobs(changed_paths(base, head))
    except (OSError, subprocess.CalledProcessError):
        print("Could not determine changed paths; running all CI jobs.")
        return ALL_JOBS


def main() -> None:
    selected = event_jobs(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("BASE_SHA", ""),
        os.environ.get("HEAD_SHA", ""),
    )
    outputs = "".join(
        f"{job}={str(job in selected).lower()}\n" for job in sorted(ALL_JOBS)
    )
    print(outputs, end="")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(outputs)


if __name__ == "__main__":
    main()
