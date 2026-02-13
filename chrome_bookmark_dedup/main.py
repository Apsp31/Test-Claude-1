#!/usr/bin/env python3
"""Chrome Bookmark Deduplicator — CLI entry point.

Reads a Chrome bookmarks file, finds and merges duplicate folder branches
and URLs, then writes a clean deduplicated file and an interactive HTML
visualization of the changes.

Usage:
    python -m chrome_bookmark_dedup <input_file> [options]

Examples:
    python -m chrome_bookmark_dedup ~/Bookmarks
    python -m chrome_bookmark_dedup ~/Bookmarks -o cleaned_bookmarks.json
    python -m chrome_bookmark_dedup ~/Bookmarks --no-viz
"""

import argparse
import sys
from pathlib import Path

from .parser import load_bookmarks, deep_copy_bookmarks, count_nodes
from .dedup import deduplicate_tree, DeduplicationStats
from .writer import write_bookmarks, write_report
from .visualize import generate_visualization


def build_parser():
    parser = argparse.ArgumentParser(
        prog="chrome-bookmark-dedup",
        description=(
            "Deduplicate Chrome bookmarks: merge duplicate folder branches, "
            "remove duplicate URLs, and consolidate import artifacts."
        ),
    )
    parser.add_argument(
        "input",
        help="Path to Chrome Bookmarks file (JSON)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path for the deduplicated bookmarks (default: <input>_deduped.json)",
    )
    parser.add_argument(
        "--report",
        help="Output path for the text report (default: <input>_report.txt)",
    )
    parser.add_argument(
        "--viz",
        help="Output path for the HTML visualization (default: <input>_visualization.html)",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Skip generating the HTML visualization",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and report without writing the deduplicated file",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    stem = input_path.stem

    # Default output paths
    out_dir = input_path.parent
    output_path = Path(args.output) if args.output else out_dir / f"{stem}_deduped.json"
    report_path = Path(args.report) if args.report else out_dir / f"{stem}_report.txt"
    viz_path = Path(args.viz) if args.viz else out_dir / f"{stem}_visualization.html"

    # Load
    print(f"Loading bookmarks from: {input_path}")
    try:
        original_data = load_bookmarks(input_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Count originals
    total_folders_orig = 0
    total_urls_orig = 0
    for root_name, root_node in original_data["roots"].items():
        if isinstance(root_node, dict):
            f, u = count_nodes(root_node)
            total_folders_orig += f
            total_urls_orig += u

    print(f"  Found {total_folders_orig} folders and {total_urls_orig} URLs")

    # Deep copy for mutation
    working_data = deep_copy_bookmarks(original_data)

    # Deduplicate
    print("Deduplicating...")
    stats = DeduplicationStats()
    deduplicate_tree(working_data, stats)

    # Print summary
    summary = stats.summary()
    print()
    print("Results:")
    print(f"  Duplicate folders merged:  {summary['duplicate_folders_merged']}")
    print(f"  Import folders processed:  {summary['import_folders_merged']}")
    print(f"  Duplicate URLs removed:    {summary['duplicate_urls_removed']}")
    print(f"  Empty folders removed:     {summary['empty_folders_removed']}")
    print(f"  Folders: {summary['total_folders_before']} -> {summary['total_folders_after']}")
    print(f"  URLs:    {summary['total_urls_before']} -> {summary['total_urls_after']}")
    removed = (
        summary["total_folders_before"]
        + summary["total_urls_before"]
        - summary["total_folders_after"]
        - summary["total_urls_after"]
    )
    print(f"  Total nodes removed: {removed}")
    print()

    # Write outputs
    if not args.dry_run:
        write_bookmarks(working_data, output_path)
        print(f"Deduplicated bookmarks written to: {output_path}")
    else:
        print("(Dry run — no output file written)")

    write_report(stats, report_path)
    print(f"Report written to: {report_path}")

    if not args.no_viz:
        generate_visualization(original_data, working_data, stats, viz_path)
        print(f"Visualization written to: {viz_path}")
        print(f"  Open in a browser: file://{viz_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
