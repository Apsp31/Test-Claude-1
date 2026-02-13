"""Core deduplication logic for Chrome bookmark trees.

Strategy:
1. At each level of the tree, find folders with the same name.
2. Merge their children recursively into a single folder.
3. Detect "imported" folder patterns (e.g. "Imported", "Bookmarks bar" nested
   inside itself, folders with "(2)" suffixes).
4. Within each folder, remove duplicate URLs (same URL string).
5. Track all changes for reporting.
"""

import re
from collections import defaultdict
from urllib.parse import urlparse, urlunparse


class DeduplicationStats:
    """Tracks statistics about what the deduplication process changed."""

    def __init__(self):
        self.duplicate_folders_merged = 0
        self.duplicate_urls_removed = 0
        self.import_folders_merged = 0
        self.empty_folders_removed = 0
        self.total_folders_before = 0
        self.total_urls_before = 0
        self.total_folders_after = 0
        self.total_urls_after = 0
        self.merge_log = []  # List of human-readable merge descriptions

    def log(self, message):
        self.merge_log.append(message)

    def summary(self):
        return {
            "duplicate_folders_merged": self.duplicate_folders_merged,
            "duplicate_urls_removed": self.duplicate_urls_removed,
            "import_folders_merged": self.import_folders_merged,
            "empty_folders_removed": self.empty_folders_removed,
            "total_folders_before": self.total_folders_before,
            "total_urls_before": self.total_urls_before,
            "total_folders_after": self.total_folders_after,
            "total_urls_after": self.total_urls_after,
        }


def normalize_url(url):
    """Normalize a URL for duplicate comparison.

    Strips trailing slashes, lowercases the scheme and host, removes
    common tracking parameters, and normalizes www prefixes.
    """
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Normalize www prefix — treat www.example.com == example.com
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # Strip trailing slash from path
        path = parsed.path.rstrip("/") if parsed.path != "/" else ""

        # Remove common tracking query params but keep meaningful ones
        query = parsed.query
        if query:
            params = query.split("&")
            tracking_prefixes = ("utm_", "fbclid", "gclid", "ref", "source")
            filtered = [
                p for p in params
                if not any(p.lower().startswith(t) for t in tracking_prefixes)
            ]
            query = "&".join(sorted(filtered))

        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return url


def normalize_folder_name(name):
    """Normalize a folder name for matching.

    Handles patterns like 'Bookmarks bar (2)', 'Imported Bookmarks',
    'Bookmarks - Imported', etc.
    """
    # Strip trailing copy indicators: (2), (3), - Copy, _copy, etc.
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)
    name = re.sub(r"\s*-\s*[Cc]opy\s*$", "", name)
    name = re.sub(r"\s*_copy\s*\d*\s*$", "", name)
    return name.strip()


# Folder names that indicate an import operation
IMPORT_FOLDER_PATTERNS = [
    re.compile(r"^Imported\b", re.IGNORECASE),
    re.compile(r"^Imported from\b", re.IGNORECASE),
    re.compile(r"^Bookmarks\s*-?\s*Imported", re.IGNORECASE),
    re.compile(r"^Chrome\s*-?\s*Imported", re.IGNORECASE),
    re.compile(r"^Firefox\s*-?\s*Imported", re.IGNORECASE),
    re.compile(r"^Safari\s*-?\s*Imported", re.IGNORECASE),
    re.compile(r"^Edge\s*-?\s*Imported", re.IGNORECASE),
    re.compile(r"^IE\s*-?\s*Imported", re.IGNORECASE),
    re.compile(r"^Imported$", re.IGNORECASE),
]


def is_import_folder(name):
    """Check if a folder name indicates it was created by a bookmark import."""
    return any(pat.match(name) for pat in IMPORT_FOLDER_PATTERNS)


def _pick_best_folder_metadata(folders):
    """Given multiple folder nodes with the same name, pick the best metadata.

    Prefers the oldest date_added (the original) and keeps the most recent
    date_modified.
    """
    best = dict(folders[0])
    for folder in folders[1:]:
        # Keep earliest date_added
        if folder.get("date_added", "0") < best.get("date_added", "0"):
            best["date_added"] = folder["date_added"]
            if "guid" in folder:
                best["guid"] = folder["guid"]
            if "id" in folder:
                best["id"] = folder["id"]
        # Keep latest date_modified
        if folder.get("date_modified", "0") > best.get("date_modified", "0"):
            best["date_modified"] = folder["date_modified"]

    # Remove children — we'll rebuild those
    best.pop("children", None)
    return best


def deduplicate_tree(data, stats=None):
    """Deduplicate an entire Chrome bookmarks data structure.

    Args:
        data: The parsed Chrome bookmarks dict (should be a deep copy).
        stats: Optional DeduplicationStats instance for tracking.

    Returns:
        The modified data dict with duplicates removed.
    """
    if stats is None:
        stats = DeduplicationStats()

    from .parser import count_nodes

    # Count before
    for root_name, root_node in data["roots"].items():
        if isinstance(root_node, dict):
            f, u = count_nodes(root_node)
            stats.total_folders_before += f
            stats.total_urls_before += u

    # Process each root
    for root_name in list(data["roots"].keys()):
        root_node = data["roots"][root_name]
        if isinstance(root_node, dict) and root_node.get("type") == "folder":
            data["roots"][root_name] = _dedup_folder(root_node, stats, path=root_name)

    # Now handle import folders at the top level of bookmark_bar and other
    for root_name in ("bookmark_bar", "other"):
        root_node = data["roots"].get(root_name)
        if root_node and root_node.get("type") == "folder":
            data["roots"][root_name] = _merge_import_folders_into_tree(
                root_node, stats, path=root_name
            )

    # Count after
    for root_name, root_node in data["roots"].items():
        if isinstance(root_node, dict):
            f, u = count_nodes(root_node)
            stats.total_folders_after += f
            stats.total_urls_after += u

    return data


def _dedup_folder(folder_node, stats, path=""):
    """Recursively deduplicate a single folder node.

    1. Group child folders by normalized name and merge duplicates.
    2. Remove duplicate URLs within this folder.
    3. Recurse into each child folder.
    4. Remove empty folders.
    """
    children = folder_node.get("children", [])
    if not children:
        return folder_node

    # --- Step 1: Merge child folders with the same normalized name ---
    folder_groups = defaultdict(list)
    url_children = []
    other_children = []

    for child in children:
        if child.get("type") == "folder":
            norm_name = normalize_folder_name(child.get("name", ""))
            folder_groups[norm_name].append(child)
        elif child.get("type") == "url":
            url_children.append(child)
        else:
            other_children.append(child)

    merged_folders = []
    for norm_name, folders in folder_groups.items():
        if len(folders) > 1:
            merged = _merge_folders(folders, stats, path=f"{path} > {norm_name}")
            stats.duplicate_folders_merged += len(folders) - 1
            stats.log(
                f"Merged {len(folders)} folders named '{folders[0].get('name', '')}' "
                f"at {path}"
            )
            merged_folders.append(merged)
        else:
            merged_folders.append(folders[0])

    # --- Step 2: Deduplicate URLs ---
    seen_urls = {}
    unique_urls = []
    for url_node in url_children:
        norm = normalize_url(url_node.get("url", ""))
        if norm not in seen_urls:
            seen_urls[norm] = url_node
            unique_urls.append(url_node)
        else:
            stats.duplicate_urls_removed += 1

    removed_url_count = len(url_children) - len(unique_urls)
    if removed_url_count > 0:
        stats.log(
            f"Removed {removed_url_count} duplicate URL(s) in '{folder_node.get('name', '')}' "
            f"at {path}"
        )

    # --- Step 3: Recurse into child folders ---
    recursed_folders = []
    for f in merged_folders:
        recursed_folders.append(_dedup_folder(f, stats, path=f"{path} > {f.get('name', '')}"))

    # --- Step 4: Remove empty folders ---
    non_empty_folders = []
    for f in recursed_folders:
        if f.get("children") or f.get("type") != "folder":
            non_empty_folders.append(f)
        else:
            stats.empty_folders_removed += 1
            stats.log(f"Removed empty folder '{f.get('name', '')}' at {path}")

    # Rebuild children: folders first, then URLs, then others
    folder_node["children"] = non_empty_folders + unique_urls + other_children
    return folder_node


def _merge_folders(folders, stats, path=""):
    """Merge multiple folder nodes (same name) into one.

    Combines all children, then deduplicates recursively.
    """
    best = _pick_best_folder_metadata(folders)

    # Collect all children from all folders
    all_children = []
    for folder in folders:
        all_children.extend(folder.get("children", []))

    best["children"] = all_children
    return best


def _merge_import_folders_into_tree(root_node, stats, path=""):
    """Find 'Imported' folders and merge their contents into the main tree.

    If an imported folder contains sub-folders that match existing top-level
    folders (e.g., an imported 'Bookmarks bar' inside 'Other bookmarks'),
    merge those sub-folders with their counterparts.
    """
    children = root_node.get("children", [])
    if not children:
        return root_node

    import_folders = []
    regular_children = []

    for child in children:
        if child.get("type") == "folder" and is_import_folder(child.get("name", "")):
            import_folders.append(child)
        else:
            regular_children.append(child)

    if not import_folders:
        return root_node

    # Build a lookup of existing folder names at this level
    existing_folders = {}
    for i, child in enumerate(regular_children):
        if child.get("type") == "folder":
            norm = normalize_folder_name(child.get("name", ""))
            existing_folders[norm] = i

    for imp_folder in import_folders:
        stats.import_folders_merged += 1
        stats.log(
            f"Processing import folder '{imp_folder.get('name', '')}' at {path}"
        )

        for imp_child in imp_folder.get("children", []):
            if imp_child.get("type") == "folder":
                norm_name = normalize_folder_name(imp_child.get("name", ""))
                if norm_name in existing_folders:
                    # Merge into existing folder
                    idx = existing_folders[norm_name]
                    target = regular_children[idx]
                    existing_children = target.get("children", [])
                    imported_children = imp_child.get("children", [])
                    target["children"] = existing_children + imported_children
                    regular_children[idx] = target
                    stats.log(
                        f"  Merged imported sub-folder '{imp_child.get('name', '')}' "
                        f"into existing folder"
                    )
                else:
                    regular_children.append(imp_child)
                    existing_folders[norm_name] = len(regular_children) - 1
            else:
                # URL or other — just add to the root level
                regular_children.append(imp_child)

    root_node["children"] = regular_children

    # Now re-deduplicate since we added content
    root_node = _dedup_folder(root_node, stats, path=path)

    return root_node
