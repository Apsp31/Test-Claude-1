"""Tkinter GUI for Chrome Bookmark Deduplicator.

Provides a graphical interface for selecting bookmark files, previewing
changes, and specifying output paths. Designed for Windows filesystem use.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from .parser import load_bookmarks, deep_copy_bookmarks, count_nodes
from .dedup import deduplicate_tree, DeduplicationStats
from .writer import write_bookmarks, write_report
from .visualize import generate_visualization


# Default Chrome bookmark locations on Windows
_WIN_CHROME_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Bookmarks",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Profile 1" / "Bookmarks",
]


def _find_default_bookmark_file():
    """Try to find the default Chrome Bookmarks file on Windows."""
    for p in _WIN_CHROME_PATHS:
        if p.exists():
            return str(p)
    return ""


class BookmarkDeduplicatorGUI:
    """Main GUI application window."""

    def __init__(self, root):
        self.root = root
        self.root.title("Chrome Bookmark Deduplicator")
        self.root.minsize(780, 680)

        # State
        self._original_data = None
        self._working_data = None
        self._stats = None

        # Colors (dark theme)
        self._bg = "#1e1e2e"
        self._fg = "#cdd6f4"
        self._accent = "#89b4fa"
        self._green = "#a6e3a1"
        self._red = "#f38ba8"
        self._surface = "#313244"
        self._overlay = "#45475a"

        self.root.configure(bg=self._bg)

        self._setup_styles()
        self._build_ui()

        # Try auto-detecting the bookmark file
        default = _find_default_bookmark_file()
        if default:
            self._var_input.set(default)
            self._auto_fill_outputs(default)

    # ------------------------------------------------------------------ #
    #  Style setup                                                        #
    # ------------------------------------------------------------------ #
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=self._bg, foreground=self._fg,
                         fieldbackground=self._surface, borderwidth=0)
        style.configure("TFrame", background=self._bg)
        style.configure("TLabel", background=self._bg, foreground=self._fg,
                         font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"),
                         foreground=self._accent)
        style.configure("Sub.TLabel", font=("Segoe UI", 9),
                         foreground="#a6adc8")
        style.configure("Stat.TLabel", font=("Segoe UI", 11, "bold"),
                         foreground=self._green)
        style.configure("TEntry", fieldbackground=self._surface,
                         foreground=self._fg, insertcolor=self._fg)
        style.configure("TButton", background=self._overlay,
                         foreground=self._fg, font=("Segoe UI", 10),
                         padding=(12, 6))
        style.map("TButton",
                   background=[("active", self._accent)],
                   foreground=[("active", "#1e1e2e")])
        style.configure("Accent.TButton", background=self._accent,
                         foreground="#1e1e2e", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton",
                   background=[("active", "#74c7ec"), ("disabled", self._overlay)],
                   foreground=[("disabled", "#6c7086")])
        style.configure("TCheckbutton", background=self._bg,
                         foreground=self._fg, font=("Segoe UI", 10))
        style.configure("TLabelframe", background=self._bg,
                         foreground=self._accent, font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background=self._bg,
                         foreground=self._accent)

    # ------------------------------------------------------------------ #
    #  UI construction                                                     #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # Main container with padding
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        # Header
        ttk.Label(outer, text="Chrome Bookmark Deduplicator",
                  style="Header.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Select a Chrome Bookmarks file, preview changes, "
                  "then save the deduplicated output.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 12))

        # ---- Input file ----
        input_frame = ttk.LabelFrame(outer, text="  Input File  ", padding=10)
        input_frame.pack(fill="x", pady=(0, 8))

        row = ttk.Frame(input_frame)
        row.pack(fill="x")
        self._var_input = tk.StringVar()
        entry_in = ttk.Entry(row, textvariable=self._var_input)
        entry_in.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse...", command=self._browse_input).pack(side="left")

        # ---- Output files ----
        output_frame = ttk.LabelFrame(outer, text="  Output Files  ", padding=10)
        output_frame.pack(fill="x", pady=(0, 8))

        self._var_output = tk.StringVar()
        self._var_report = tk.StringVar()
        self._var_viz = tk.StringVar()
        self._var_skip_viz = tk.BooleanVar(value=False)

        for label_text, var, save_type in [
            ("Deduplicated:", self._var_output, "deduped"),
            ("Report:", self._var_report, "report"),
            ("Visualization:", self._var_viz, "viz"),
        ]:
            r = ttk.Frame(output_frame)
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=label_text, width=14, anchor="e").pack(side="left")
            ttk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True, padx=(4, 8))
            ttk.Button(r, text="Browse...",
                       command=lambda v=var, s=save_type: self._browse_output(v, s)).pack(side="left")

        ttk.Checkbutton(output_frame, text="Skip HTML visualization",
                        variable=self._var_skip_viz).pack(anchor="w", pady=(6, 0))

        # ---- Action buttons ----
        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill="x", pady=(0, 8))

        self._btn_analyze = ttk.Button(btn_frame, text="Analyze",
                                       command=self._run_analysis)
        self._btn_analyze.pack(side="left", padx=(0, 8))

        self._btn_save = ttk.Button(btn_frame, text="Save Deduplicated Bookmarks",
                                    style="Accent.TButton",
                                    command=self._run_save, state="disabled")
        self._btn_save.pack(side="left", padx=(0, 8))

        self._btn_open_viz = ttk.Button(btn_frame, text="Open Visualization",
                                        command=self._open_visualization,
                                        state="disabled")
        self._btn_open_viz.pack(side="left")

        # ---- Preview / results area ----
        preview_frame = ttk.LabelFrame(outer, text="  Changes Preview  ", padding=10)
        preview_frame.pack(fill="both", expand=True)

        # Stats summary row
        self._stats_frame = ttk.Frame(preview_frame)
        self._stats_frame.pack(fill="x", pady=(0, 8))

        self._lbl_status = ttk.Label(self._stats_frame,
                                     text="Load a bookmark file and click Analyze to preview changes.",
                                     style="Sub.TLabel")
        self._lbl_status.pack(anchor="w")

        # Stats grid (hidden until analysis)
        self._stats_grid = ttk.Frame(preview_frame)

        # Detailed log
        log_label = ttk.Label(preview_frame, text="Merge Log:", style="Sub.TLabel")
        log_label.pack(anchor="w", pady=(4, 2))

        log_container = ttk.Frame(preview_frame)
        log_container.pack(fill="both", expand=True)

        self._log_text = tk.Text(log_container, wrap="word", height=10,
                                 bg=self._surface, fg=self._fg,
                                 insertbackground=self._fg,
                                 selectbackground=self._accent,
                                 font=("Consolas", 9), relief="flat",
                                 padx=8, pady=8, state="disabled")
        scrollbar = ttk.Scrollbar(log_container, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log_text.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------------ #
    #  File dialogs                                                        #
    # ------------------------------------------------------------------ #
    def _browse_input(self):
        filetypes = [
            ("Chrome Bookmarks", "Bookmarks"),
            ("JSON files", "*.json"),
            ("All files", "*.*"),
        ]
        initial_dir = None
        current = self._var_input.get().strip()
        if current:
            p = Path(current)
            if p.parent.exists():
                initial_dir = str(p.parent)

        path = filedialog.askopenfilename(
            title="Select Chrome Bookmarks File",
            filetypes=filetypes,
            initialdir=initial_dir,
        )
        if path:
            self._var_input.set(path)
            self._auto_fill_outputs(path)

    def _browse_output(self, var, save_type):
        ext_map = {
            "deduped": ("JSON files", "*.json"),
            "report": ("Text files", "*.txt"),
            "viz": ("HTML files", "*.html"),
        }
        desc, pattern = ext_map.get(save_type, ("All files", "*.*"))
        path = filedialog.asksaveasfilename(
            title=f"Save {desc.split()[0]} file",
            filetypes=[(desc, pattern), ("All files", "*.*")],
            defaultextension=pattern.replace("*", ""),
        )
        if path:
            var.set(path)

    def _auto_fill_outputs(self, input_path):
        """Pre-fill output paths based on the input file."""
        p = Path(input_path)
        stem = p.stem
        out_dir = p.parent
        if not self._var_output.get():
            self._var_output.set(str(out_dir / f"{stem}_deduped.json"))
        if not self._var_report.get():
            self._var_report.set(str(out_dir / f"{stem}_report.txt"))
        if not self._var_viz.get():
            self._var_viz.set(str(out_dir / f"{stem}_visualization.html"))

    # ------------------------------------------------------------------ #
    #  Analysis                                                            #
    # ------------------------------------------------------------------ #
    def _run_analysis(self):
        input_path = self._var_input.get().strip()
        if not input_path:
            messagebox.showwarning("No Input", "Please select a Chrome Bookmarks file first.")
            return

        self._btn_analyze.configure(state="disabled")
        self._btn_save.configure(state="disabled")
        self._btn_open_viz.configure(state="disabled")
        self._lbl_status.configure(text="Analyzing...", style="Sub.TLabel")
        self.root.update_idletasks()

        # Run in a thread so the UI doesn't freeze
        threading.Thread(target=self._do_analysis, args=(input_path,), daemon=True).start()

    def _do_analysis(self, input_path):
        try:
            original_data = load_bookmarks(input_path)
        except (FileNotFoundError, ValueError) as e:
            self.root.after(0, lambda: self._on_analysis_error(str(e)))
            return
        except Exception as e:
            self.root.after(0, lambda: self._on_analysis_error(f"Failed to load: {e}"))
            return

        working_data = deep_copy_bookmarks(original_data)
        stats = DeduplicationStats()
        deduplicate_tree(working_data, stats)

        self._original_data = original_data
        self._working_data = working_data
        self._stats = stats

        self.root.after(0, self._on_analysis_done)

    def _on_analysis_error(self, message):
        self._btn_analyze.configure(state="normal")
        self._lbl_status.configure(text=f"Error: {message}")
        messagebox.showerror("Error", message)

    def _on_analysis_done(self):
        self._btn_analyze.configure(state="normal")
        self._btn_save.configure(state="normal")

        stats = self._stats
        summary = stats.summary()
        removed = (
            summary["total_folders_before"] + summary["total_urls_before"]
            - summary["total_folders_after"] - summary["total_urls_after"]
        )

        # Update stats grid
        for w in self._stats_grid.winfo_children():
            w.destroy()
        self._stats_grid.pack(fill="x", pady=(0, 8))

        stat_items = [
            ("Folders", f"{summary['total_folders_before']}  ->  {summary['total_folders_after']}"),
            ("URLs", f"{summary['total_urls_before']}  ->  {summary['total_urls_after']}"),
            ("Folders merged", str(summary["duplicate_folders_merged"])),
            ("Duplicate URLs removed", str(summary["duplicate_urls_removed"])),
            ("Import folders processed", str(summary["import_folders_merged"])),
            ("Empty folders removed", str(summary["empty_folders_removed"])),
            ("Total nodes removed", str(removed)),
        ]

        for i, (label, value) in enumerate(stat_items):
            row = i // 3
            col = i % 3
            frame = ttk.Frame(self._stats_grid, padding=6)
            frame.grid(row=row, column=col, padx=4, pady=2, sticky="nsew")
            ttk.Label(frame, text=value, style="Stat.TLabel").pack(anchor="w")
            ttk.Label(frame, text=label, style="Sub.TLabel").pack(anchor="w")
            self._stats_grid.columnconfigure(col, weight=1)

        if removed == 0:
            self._lbl_status.configure(
                text="No duplicates found — your bookmarks are already clean!",
                style="Stat.TLabel")
        else:
            self._lbl_status.configure(
                text=f"Found {removed} duplicate nodes to remove. Click Save to write output.",
                style="Stat.TLabel")

        # Fill log
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        if stats.merge_log:
            self._log_text.insert("end", "\n".join(stats.merge_log))
        else:
            self._log_text.insert("end", "(No changes to report)")
        self._log_text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    #  Save                                                                #
    # ------------------------------------------------------------------ #
    def _run_save(self):
        if self._working_data is None:
            messagebox.showwarning("No Data", "Run Analyze first.")
            return

        output_path = self._var_output.get().strip()
        report_path = self._var_report.get().strip()
        viz_path = self._var_viz.get().strip()
        skip_viz = self._var_skip_viz.get()

        if not output_path:
            messagebox.showwarning("Missing Path", "Please specify an output file path.")
            return

        self._btn_save.configure(state="disabled")
        self._lbl_status.configure(text="Saving...")
        self.root.update_idletasks()

        threading.Thread(
            target=self._do_save,
            args=(output_path, report_path, viz_path, skip_viz),
            daemon=True,
        ).start()

    def _do_save(self, output_path, report_path, viz_path, skip_viz):
        try:
            write_bookmarks(self._working_data, output_path)

            if report_path:
                write_report(self._stats, report_path)

            if viz_path and not skip_viz:
                generate_visualization(
                    self._original_data, self._working_data, self._stats, viz_path
                )

            self.root.after(0, lambda: self._on_save_done(output_path, viz_path, skip_viz))
        except Exception as e:
            self.root.after(0, lambda: self._on_save_error(str(e)))

    def _on_save_error(self, message):
        self._btn_save.configure(state="normal")
        self._lbl_status.configure(text=f"Save error: {message}")
        messagebox.showerror("Save Error", message)

    def _on_save_done(self, output_path, viz_path, skip_viz):
        self._btn_save.configure(state="normal")
        if viz_path and not skip_viz:
            self._btn_open_viz.configure(state="normal")
            self._saved_viz_path = viz_path

        self._lbl_status.configure(text=f"Saved to {output_path}")
        messagebox.showinfo("Done", f"Deduplicated bookmarks saved to:\n{output_path}")

    # ------------------------------------------------------------------ #
    #  Open visualization                                                  #
    # ------------------------------------------------------------------ #
    def _open_visualization(self):
        path = getattr(self, "_saved_viz_path", None)
        if not path:
            return
        import webbrowser
        webbrowser.open(Path(path).resolve().as_uri())


def run_gui():
    """Launch the GUI application."""
    root = tk.Tk()

    # Set icon if possible (suppress errors on non-Windows)
    try:
        root.iconbitmap(default="")
    except tk.TclError:
        pass

    BookmarkDeduplicatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
