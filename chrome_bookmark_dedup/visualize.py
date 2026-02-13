"""Generate an interactive HTML visualization of the bookmark deduplication."""

import json
from pathlib import Path


def _build_vis_tree(node, max_depth=6, depth=0):
    """Convert a bookmark node into a simplified tree for D3 visualization."""
    if depth > max_depth:
        return None

    name = node.get("name", "(unnamed)")
    node_type = node.get("type", "unknown")

    result = {"name": name, "type": node_type}

    if node_type == "url":
        result["url"] = node.get("url", "")
        return result

    children = node.get("children", [])
    vis_children = []

    # Limit children shown to avoid overwhelming the visualization
    folder_children = [c for c in children if c.get("type") == "folder"]
    url_children = [c for c in children if c.get("type") == "url"]

    for child in folder_children:
        vis_child = _build_vis_tree(child, max_depth, depth + 1)
        if vis_child:
            vis_children.append(vis_child)

    # Show up to 15 URLs per folder in the vis, summarize the rest
    for child in url_children[:15]:
        vis_children.append({
            "name": child.get("name", "(unnamed)"),
            "type": "url",
            "url": child.get("url", ""),
        })

    if len(url_children) > 15:
        vis_children.append({
            "name": f"... and {len(url_children) - 15} more URLs",
            "type": "summary",
        })

    if vis_children:
        result["children"] = vis_children
    result["_childCount"] = len(children)

    return result


def _build_roots_tree(data, label, max_depth=6):
    """Build a top-level tree node from the bookmark roots."""
    root = {"name": label, "type": "root", "children": []}

    for root_name in ("bookmark_bar", "other", "synced"):
        node = data.get("roots", {}).get(root_name)
        if node and isinstance(node, dict) and node.get("type") == "folder":
            vis = _build_vis_tree(node, max_depth)
            if vis:
                root["children"].append(vis)

    return root


def generate_visualization(before_data, after_data, stats, output_path):
    """Generate an interactive HTML file showing before/after trees and stats.

    Args:
        before_data: Original bookmark data (before dedup).
        after_data: Deduplicated bookmark data.
        stats: DeduplicationStats instance.
        output_path: Where to write the HTML file.

    Returns:
        Path: The path to the generated HTML file.
    """
    before_tree = _build_roots_tree(before_data, "Before (Original)")
    after_tree = _build_roots_tree(after_data, "After (Deduplicated)")
    summary = stats.summary()
    log_entries = stats.merge_log[:200]  # Cap log display

    html = _generate_html(before_tree, after_tree, summary, log_entries)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path


def _generate_html(before_tree, after_tree, summary, log_entries):
    """Generate the full HTML document."""
    before_json = json.dumps(before_tree, indent=2)
    after_json = json.dumps(after_tree, indent=2)
    summary_json = json.dumps(summary, indent=2)
    log_json = json.dumps(log_entries, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chrome Bookmark Deduplication Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f1117;
    color: #e1e4e8;
    line-height: 1.5;
  }}
  .header {{
    background: linear-gradient(135deg, #1a1e2e 0%, #2d1b4e 100%);
    padding: 30px 40px;
    border-bottom: 2px solid #30363d;
  }}
  .header h1 {{
    font-size: 28px;
    font-weight: 700;
    color: #f0f6fc;
  }}
  .header p {{ color: #8b949e; margin-top: 6px; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}

  /* Stats cards */
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .stat-card {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    transition: transform 0.2s;
  }}
  .stat-card:hover {{ transform: translateY(-2px); }}
  .stat-card .value {{
    font-size: 36px;
    font-weight: 700;
    display: block;
  }}
  .stat-card .label {{
    font-size: 13px;
    color: #8b949e;
    margin-top: 4px;
  }}
  .stat-card.green .value {{ color: #3fb950; }}
  .stat-card.red .value {{ color: #f85149; }}
  .stat-card.blue .value {{ color: #58a6ff; }}
  .stat-card.purple .value {{ color: #bc8cff; }}

  /* Comparison section */
  .comparison {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 32px;
  }}
  @media (max-width: 900px) {{ .comparison {{ grid-template-columns: 1fr; }} }}
  .tree-panel {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    overflow: hidden;
  }}
  .tree-panel h2 {{
    padding: 16px 20px;
    font-size: 16px;
    border-bottom: 1px solid #30363d;
  }}
  .tree-panel.before h2 {{ background: #2d1b1b; color: #f85149; }}
  .tree-panel.after h2 {{ background: #1b2d1b; color: #3fb950; }}
  .tree-content {{
    padding: 12px 8px;
    max-height: 600px;
    overflow-y: auto;
  }}

  /* Tree rendering */
  .tree-node {{ padding-left: 20px; }}
  .tree-label {{
    cursor: pointer;
    padding: 3px 8px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    white-space: nowrap;
  }}
  .tree-label:hover {{ background: #21262d; }}
  .tree-label .icon {{ font-size: 14px; flex-shrink: 0; }}
  .tree-label.folder .icon {{ color: #e3b341; }}
  .tree-label.url .icon {{ color: #58a6ff; }}
  .tree-label.summary {{ color: #8b949e; font-style: italic; }}
  .tree-label .count {{
    color: #8b949e;
    font-size: 11px;
    margin-left: 4px;
  }}
  .tree-children {{ display: none; }}
  .tree-children.open {{ display: block; }}

  /* Log section */
  .log-section {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 24px;
  }}
  .log-section h2 {{
    padding: 16px 20px;
    font-size: 16px;
    border-bottom: 1px solid #30363d;
    background: #1b2330;
    color: #58a6ff;
    cursor: pointer;
    user-select: none;
  }}
  .log-section h2:hover {{ background: #1f2937; }}
  .log-entries {{
    max-height: 400px;
    overflow-y: auto;
    padding: 12px 20px;
    display: none;
  }}
  .log-entries.open {{ display: block; }}
  .log-entry {{
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    padding: 4px 0;
    color: #c9d1d9;
    border-bottom: 1px solid #21262d;
  }}

  /* Bar chart */
  .bar-chart {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 24px;
    margin-bottom: 32px;
  }}
  .bar-chart h2 {{
    font-size: 16px;
    margin-bottom: 20px;
    color: #f0f6fc;
  }}
  .bar-row {{
    display: flex;
    align-items: center;
    margin-bottom: 12px;
    gap: 12px;
  }}
  .bar-label {{
    width: 120px;
    font-size: 13px;
    text-align: right;
    color: #8b949e;
    flex-shrink: 0;
  }}
  .bar-track {{
    flex: 1;
    height: 28px;
    background: #21262d;
    border-radius: 6px;
    overflow: hidden;
    position: relative;
  }}
  .bar-fill {{
    height: 100%;
    border-radius: 6px;
    display: flex;
    align-items: center;
    padding-left: 10px;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
    transition: width 1s ease-out;
  }}
  .bar-fill.before {{ background: linear-gradient(90deg, #d73a49, #f85149); }}
  .bar-fill.after {{ background: linear-gradient(90deg, #238636, #3fb950); }}

  /* Scrollbar */
  ::-webkit-scrollbar {{ width: 8px; }}
  ::-webkit-scrollbar-track {{ background: #0d1117; }}
  ::-webkit-scrollbar-thumb {{ background: #30363d; border-radius: 4px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: #484f58; }}
</style>
</head>
<body>

<div class="header">
  <h1>Chrome Bookmark Deduplication Report</h1>
  <p>Analysis of duplicate folders, URLs, and import artifacts</p>
</div>

<div class="container">

  <!-- Stats cards -->
  <div class="stats-grid" id="stats-grid"></div>

  <!-- Bar chart comparison -->
  <div class="bar-chart">
    <h2>Before vs After Comparison</h2>
    <div id="bar-chart-content"></div>
  </div>

  <!-- Side-by-side trees -->
  <div class="comparison">
    <div class="tree-panel before">
      <h2>Before — Original Bookmarks</h2>
      <div class="tree-content" id="tree-before"></div>
    </div>
    <div class="tree-panel after">
      <h2>After — Deduplicated</h2>
      <div class="tree-content" id="tree-after"></div>
    </div>
  </div>

  <!-- Merge log -->
  <div class="log-section">
    <h2 id="log-toggle">Detailed Merge Log (click to expand)</h2>
    <div class="log-entries" id="log-entries"></div>
  </div>

</div>

<script>
const beforeTree = {before_json};
const afterTree = {after_json};
const summary = {summary_json};
const logEntries = {log_json};

// --- Stats cards ---
function renderStats() {{
  const grid = document.getElementById('stats-grid');
  const removed = (summary.total_folders_before + summary.total_urls_before) -
                  (summary.total_folders_after + summary.total_urls_after);
  const pct = summary.total_urls_before > 0
    ? Math.round((summary.duplicate_urls_removed / summary.total_urls_before) * 100) : 0;
  const cards = [
    {{ value: summary.duplicate_folders_merged, label: 'Folders Merged', cls: 'purple' }},
    {{ value: summary.duplicate_urls_removed, label: 'Duplicate URLs Removed', cls: 'red' }},
    {{ value: summary.import_folders_merged, label: 'Import Folders Processed', cls: 'blue' }},
    {{ value: summary.empty_folders_removed, label: 'Empty Folders Removed', cls: 'blue' }},
    {{ value: removed, label: 'Total Nodes Removed', cls: 'green' }},
    {{ value: pct + '%', label: 'URL Duplication Rate', cls: 'red' }},
  ];
  grid.innerHTML = cards.map(c => `
    <div class="stat-card ${{c.cls}}">
      <span class="value">${{c.value}}</span>
      <span class="label">${{c.label}}</span>
    </div>
  `).join('');
}}

// --- Bar chart ---
function renderBarChart() {{
  const container = document.getElementById('bar-chart-content');
  const maxVal = Math.max(
    summary.total_folders_before, summary.total_folders_after,
    summary.total_urls_before, summary.total_urls_after, 1
  );
  const rows = [
    {{ label: 'Folders (before)', value: summary.total_folders_before, cls: 'before' }},
    {{ label: 'Folders (after)', value: summary.total_folders_after, cls: 'after' }},
    {{ label: 'URLs (before)', value: summary.total_urls_before, cls: 'before' }},
    {{ label: 'URLs (after)', value: summary.total_urls_after, cls: 'after' }},
  ];
  container.innerHTML = rows.map(r => {{
    const pct = Math.max((r.value / maxVal) * 100, 2);
    return `
      <div class="bar-row">
        <div class="bar-label">${{r.label}}</div>
        <div class="bar-track">
          <div class="bar-fill ${{r.cls}}" style="width:${{pct}}%">${{r.value}}</div>
        </div>
      </div>
    `;
  }}).join('');
}}

// --- Tree rendering ---
function renderTree(node, container, depth) {{
  depth = depth || 0;
  const div = document.createElement('div');
  div.className = 'tree-node';

  const label = document.createElement('div');
  label.className = 'tree-label ' + (node.type || '');

  if (node.type === 'folder' || node.type === 'root') {{
    const childCount = node._childCount || (node.children ? node.children.length : 0);
    label.innerHTML = `<span class="icon">${{depth === 0 ? '&#128218;' : '&#128193;'}}</span>`
      + `${{escHtml(node.name)}} <span class="count">(${{childCount}})</span>`;
    div.appendChild(label);

    if (node.children && node.children.length > 0) {{
      const childContainer = document.createElement('div');
      childContainer.className = 'tree-children' + (depth < 1 ? ' open' : '');
      node.children.forEach(c => renderTree(c, childContainer, depth + 1));
      div.appendChild(childContainer);

      label.addEventListener('click', () => {{
        childContainer.classList.toggle('open');
      }});
    }}
  }} else if (node.type === 'url') {{
    label.innerHTML = `<span class="icon">&#128279;</span>${{escHtml(node.name)}}`;
    label.title = node.url || '';
    div.appendChild(label);
  }} else if (node.type === 'summary') {{
    label.innerHTML = escHtml(node.name);
    div.appendChild(label);
  }}

  container.appendChild(div);
}}

function escHtml(s) {{
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}}

// --- Log ---
function renderLog() {{
  const container = document.getElementById('log-entries');
  container.innerHTML = logEntries.map(e =>
    `<div class="log-entry">${{escHtml(e)}}</div>`
  ).join('');

  document.getElementById('log-toggle').addEventListener('click', () => {{
    container.classList.toggle('open');
  }});
}}

// --- Init ---
renderStats();
renderBarChart();
renderTree(beforeTree, document.getElementById('tree-before'));
renderTree(afterTree, document.getElementById('tree-after'));
renderLog();
</script>
</body>
</html>"""
