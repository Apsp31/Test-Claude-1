"""Write deduplicated bookmarks back to Chrome's JSON format."""

import json
from pathlib import Path


def write_bookmarks(data, filepath):
    """Write bookmark data to a JSON file in Chrome's format.

    Args:
        data: The bookmark data structure.
        filepath: Output file path.

    Returns:
        Path: The path the file was written to.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Chrome uses 3-space indentation and no trailing newline quirks
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=3, ensure_ascii=False)
        f.write("\n")

    return path


def write_report(stats, filepath):
    """Write a human-readable deduplication report.

    Args:
        stats: DeduplicationStats instance.
        filepath: Output file path for the report.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 60,
        "  Chrome Bookmark Deduplication Report",
        "=" * 60,
        "",
        "SUMMARY",
        "-" * 40,
        f"  Folders before:            {stats.total_folders_before:>6}",
        f"  Folders after:             {stats.total_folders_after:>6}",
        f"  URLs before:               {stats.total_urls_before:>6}",
        f"  URLs after:                {stats.total_urls_after:>6}",
        "",
        f"  Duplicate folders merged:  {stats.duplicate_folders_merged:>6}",
        f"  Import folders processed:  {stats.import_folders_merged:>6}",
        f"  Duplicate URLs removed:    {stats.duplicate_urls_removed:>6}",
        f"  Empty folders removed:     {stats.empty_folders_removed:>6}",
        "",
        f"  Total nodes removed:       "
        f"{(stats.total_folders_before + stats.total_urls_before) - (stats.total_folders_after + stats.total_urls_after):>6}",
        "",
    ]

    if stats.merge_log:
        lines.append("DETAILED LOG")
        lines.append("-" * 40)
        for entry in stats.merge_log:
            lines.append(f"  {entry}")
        lines.append("")

    lines.append("=" * 60)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return path
