"""Clean cache script.

This script recursively walks through the codebase and deletes all Python
cache files and directories, such as __pycache__, .pyc files, and test caches.
"""

import os
import shutil
from pathlib import Path


def clean_cache(root_dir: Path) -> None:
    """Recursively removes cache directories and files.

    Args:
        root_dir: The root directory to start cleaning from.
    """
    # Target directories and file extensions to remove
    target_dirs = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ipynb_checkpoints",
        "build",
        "dist",
        "*.egg-info",
    }
    target_exts = {".pyc", ".pyo", ".pyd", ".opt-1.pyc", ".opt-2.pyc"}
    target_files = {".DS_Store", "pip-log.txt", ".coverage", "dump.rdb"}

    deleted_dirs = 0
    deleted_files = 0

    print(f"Starting cache cleanup in: {root_dir}\n")

    # Walk bottom-up so deleting directories doesn't mess up the iteration
    for root, dirs, files in os.walk(root_dir, topdown=False):
        current_dir = Path(root)

        # Skip .git and node_modules entirely to save time
        if ".git" in current_dir.parts or "node_modules" in current_dir.parts:
            continue

        # 1. Delete matching cache files
        for file_name in files:
            is_target = (
                any(file_name.endswith(ext) for ext in target_exts) or
                file_name in target_files
            )
            if is_target:
                file_path = current_dir / file_name
                try:
                    file_path.unlink()
                    print(f"Removed file: {file_path.relative_to(root_dir)}")
                    deleted_files += 1
                except Exception as exc:  # pylint: disable=broad-except
                    print(f"Failed to delete file {file_path}: {exc}")

        # 2. Delete matching cache directories
        for dir_name in dirs:
            is_target_dir = (
                dir_name in target_dirs or
                any(dir_name.endswith(ext) for ext in [".egg-info"])
            )
            if is_target_dir:
                dir_path = current_dir / dir_name
                try:
                    shutil.rmtree(dir_path)
                    print(f"Removed directory: {dir_path.relative_to(root_dir)}")
                    deleted_dirs += 1
                except Exception as exc:  # pylint: disable=broad-except
                    print(f"Failed to delete directory {dir_path}: {exc}")

    print("\nCleanup Complete!")
    print(f"Removed {deleted_dirs} cache directories.")
    print(f"Removed {deleted_files} cache files.")


if __name__ == "__main__":
    # Start cleanup from the root directory (where this script is located)
    project_root = Path(__file__).parent.resolve()
    clean_cache(project_root)
