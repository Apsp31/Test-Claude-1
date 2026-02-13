"""Parse Chrome bookmark JSON files into an internal tree representation."""

import json
import copy
from pathlib import Path


def load_bookmarks(filepath):
    """Load and validate a Chrome bookmarks JSON file.

    Args:
        filepath: Path to the Chrome Bookmarks file.

    Returns:
        dict: The parsed bookmark data structure.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file isn't a valid Chrome bookmarks file.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Bookmark file not found: {filepath}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "roots" not in data:
        raise ValueError(
            "Invalid Chrome bookmarks file: missing 'roots' key. "
            "Expected a file from ~/.config/google-chrome/Default/Bookmarks"
        )

    if "version" not in data:
        raise ValueError("Invalid Chrome bookmarks file: missing 'version' key.")

    return data


def deep_copy_bookmarks(data):
    """Create a deep copy of the bookmark data for safe mutation."""
    return copy.deepcopy(data)


def count_nodes(node):
    """Count total folders and URLs in a bookmark subtree.

    Returns:
        tuple: (folder_count, url_count)
    """
    if node.get("type") == "url":
        return 0, 1

    folders = 1 if node.get("type") == "folder" else 0
    urls = 0

    for child in node.get("children", []):
        cf, cu = count_nodes(child)
        folders += cf
        urls += cu

    return folders, urls


def collect_all_urls(node):
    """Collect all URLs from a bookmark subtree.

    Returns:
        list of dict: Each dict has 'url', 'name', and 'path' keys.
    """
    results = []
    _collect_urls_recursive(node, [], results)
    return results


def _collect_urls_recursive(node, path, results):
    current_path = path + [node.get("name", "")]

    if node.get("type") == "url":
        results.append({
            "url": node.get("url", ""),
            "name": node.get("name", ""),
            "path": " > ".join(current_path),
        })
        return

    for child in node.get("children", []):
        _collect_urls_recursive(child, current_path, results)


def get_tree_depth(node, depth=0):
    """Get the maximum depth of the bookmark tree."""
    if node.get("type") == "url":
        return depth

    max_depth = depth
    for child in node.get("children", []):
        child_depth = get_tree_depth(child, depth + 1)
        max_depth = max(max_depth, child_depth)

    return max_depth
