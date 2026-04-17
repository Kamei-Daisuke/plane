"""Rewrite Bitbucket-server URLs to AWS CodeCommit URLs.

Assumptions:
  - /tmp/codecommit_repos.tsv  (two columns: profile<TAB>repository_name)
    is present in the api container. It is the authoritative set of repos
    available in CodeCommit.
  - The region for every migrated repo is ap-northeast-1.

Mappings applied (lowercase repo name):
  - /projects/<KEY>/repos/<REPO>/browse(/<PATH>)?(\?at=refs%2Fheads%2F<BR>)?
      -> CodeCommit repo browse URL, optionally with branch+path.
  - /projects/<KEY>/repos/<REPO>/commits/<HASH>
      -> CodeCommit repo commit URL.
  - /projects/<KEY>/repos/<REPO>/pull-requests/<N>
      -> CodeCommit repo browse URL (no PR equivalent).
  - /scm/<KEY>/<REPO>.git (optionally with port 7990) -> git-codecommit
    clone URL.

Anything outside those patterns (Bitbucket admin, dashboard, plugins, or
repos that are not in CodeCommit) is left untouched.

Env:
  DRY_RUN=1  Print statistics without touching the DB.
"""
import os
import re
from collections import Counter
from urllib.parse import unquote

from django.db import connection, transaction


DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "yes")
REGION = "ap-northeast-1"
CC_CONSOLE = f"https://{REGION}.console.aws.amazon.com/codesuite/codecommit/repositories"
CC_GIT = f"https://git-codecommit.{REGION}.amazonaws.com/v1/repos"


def load_codecommit_repos(path: str):
    """Return set of repository names (lowercase) available in CodeCommit."""
    repos = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1]:
                repos.add(parts[1].lower())
    return repos


def build_cc_browse_url(repo: str, path: str | None, branch: str | None) -> str:
    """Construct a CodeCommit browse URL."""
    base = f"{CC_CONSOLE}/{repo}/browse"
    if path:
        branch = branch or "master"
        base += f"/refs/heads/{branch}/--/{path.lstrip('/')}"
    base += f"?region={REGION}"
    return base


def build_cc_commit_url(repo: str, commit_hash: str) -> str:
    return f"{CC_CONSOLE}/{repo}/commit/{commit_hash}?region={REGION}"


def build_cc_git_url(repo: str) -> str:
    return f"{CC_GIT}/{repo}"


def rewrite_bitbucket(html: str, known_repos: set, stats: Counter) -> str:
    if not html or "bitbucket.aruhi-corp" not in html:
        return html

    # 1. /projects/<KEY>/repos/<REPO>/browse[/<PATH>][?at=refs%2Fheads%2F<BRANCH>]
    def _browse(m):
        repo = m.group(2).lower()
        if repo not in known_repos:
            stats["unknown_repo"] += 1
            return m.group(0)
        path = m.group(3) or ""
        qs = m.group(4) or ""
        branch_m = re.search(r"at=refs(?:%2F|/)heads(?:%2F|/)([^&\"#]+)", qs)
        branch = unquote(branch_m.group(1)) if branch_m else None
        stats["browse_rewritten"] += 1
        return build_cc_browse_url(repo, path.lstrip("/"), branch)

    html = re.sub(
        r"https?://bitbucket\.aruhi-corp\.co\.jp(?::\d+)?/projects/([A-Z0-9_-]+)/repos/([a-zA-Z0-9_.-]+)/browse(/[^\"<\s>?#]*)?(\?[^\"<\s>]*)?",
        _browse,
        html,
    )

    # 2. /projects/<KEY>/repos/<REPO>/commits/<HASH>
    def _commit(m):
        repo = m.group(2).lower()
        if repo not in known_repos:
            stats["unknown_repo"] += 1
            return m.group(0)
        stats["commit_rewritten"] += 1
        return build_cc_commit_url(repo, m.group(3))

    html = re.sub(
        r"https?://bitbucket\.aruhi-corp\.co\.jp(?::\d+)?/projects/([A-Z0-9_-]+)/repos/([a-zA-Z0-9_.-]+)/commits/([0-9a-f]{7,40})",
        _commit,
        html,
    )

    # 3. /projects/<KEY>/repos/<REPO>/pull-requests/...  (no direct equivalent)
    def _pr(m):
        repo = m.group(2).lower()
        if repo not in known_repos:
            stats["unknown_repo"] += 1
            return m.group(0)
        stats["pr_rewritten"] += 1
        return build_cc_browse_url(repo, None, None)

    html = re.sub(
        r"https?://bitbucket\.aruhi-corp\.co\.jp(?::\d+)?/projects/([A-Z0-9_-]+)/repos/([a-zA-Z0-9_.-]+)/pull-requests/[^\"<\s>]*",
        _pr,
        html,
    )

    # 4. /scm/<key>/<repo>.git  (git clone)
    def _scm(m):
        repo = m.group(2).lower()
        if repo not in known_repos:
            stats["unknown_repo"] += 1
            return m.group(0)
        stats["git_rewritten"] += 1
        return build_cc_git_url(repo)

    html = re.sub(
        r"https?://bitbucket\.aruhi-corp\.co\.jp(?::\d+)?/scm/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)\.git",
        _scm,
        html,
    )

    return html


def main():
    print(f"DRY_RUN={DRY_RUN}")
    known_repos = load_codecommit_repos("/tmp/codecommit_repos.tsv")
    print(f"CodeCommit repos loaded: {len(known_repos)}")

    cursor = connection.cursor()
    stats = Counter()
    rows_changed = 0

    for tbl, col, id_col in [
        ("pages", "description_html", "id"),
        ("issues", "description_html", "id"),
        ("issue_comments", "comment_html", "id"),
    ]:
        cursor.execute(
            f"SELECT {id_col}, {col} FROM {tbl} "
            f"WHERE deleted_at IS NULL AND {col} LIKE %s",
            ["%bitbucket.aruhi-corp%"],
        )
        rows = cursor.fetchall()
        changed_here = 0
        for row in rows:
            html = row[1] or ""
            new_html = rewrite_bitbucket(html, known_repos, stats)
            if new_html != html:
                changed_here += 1
                if not DRY_RUN:
                    cursor.execute(
                        f"UPDATE {tbl} SET {col}=%s WHERE {id_col}=%s",
                        [new_html, row[0]],
                    )
        rows_changed += changed_here
        print(f"{tbl}: scanned {len(rows)} rows, changed {changed_here}")

    print(f"\nTotal rows changed: {rows_changed}")
    for k, v in stats.most_common():
        print(f"  {k}: {v}")


with transaction.atomic():
    main()
    if DRY_RUN:
        transaction.set_rollback(True)
