"""Represents current userbot version"""

__version__ = (1, 0, 0)

import os

NO_GIT = os.environ.get("HIKKARI_NO_GIT") == "1"
if not NO_GIT:
    import git
else:
    git = None
from ._internal import (check_commit_ancestor, get_branch_name,
                        reset_to_master, restart, restore_worktree)

if NO_GIT:
    branch = "master"
else:
    try:
        assert git is not None
        with git.Repo(
            path=os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ) as repo:
            branch = repo.active_branch.name
    except Exception:
        branch = "master"