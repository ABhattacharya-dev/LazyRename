"""Run with: streamlit run app.py"""

from pathlib import Path

import streamlit as st

from lazyrename.core import (DEFAULT_LOG, RenameError, apply_batch, extract_content,
                             latest_undoable, scan, undo_latest)
from lazyrename.ollama import available_models, suggest_name

st.set_page_config(page_title="LazyRename", page_icon="🦥", layout="wide")
st.markdown("""
<style>
  .block-container {max-width: 1120px; padding-top: 2rem;}
  h1, h2, h3 {letter-spacing: -.035em;}
  [data-testid="stMetric"] {background:#f5f4ee; border:1px solid #e5e4d9; border-radius:12px; padding:14px;}
  .stButton button[kind="primary"] {background:#315a48; border-color:#315a48;}
</style>
""", unsafe_allow_html=True)

st.title("🦥 LazyRename")
st.caption("Meaningful names from file contents, with a preview and a way back. Your files stay on this computer.")

with st.sidebar:
    st.header("Local setup")
    st.markdown("1. Install [Ollama](https://ollama.com/download).\n2. In PowerShell: `ollama pull gemma3:4b`.\n3. Keep Ollama running, then refresh models below.")
    if st.button("Refresh models"):
        st.rerun()
    try:
        models = available_models()
        if models:
            st.success("Ollama connected")
            model = st.selectbox("Installed instruct model", models)
        else:
            st.warning("Ollama is running, but no models are installed. Run `ollama pull gemma3:4b`.")
            model = None
    except RenameError as exc:
        st.error(str(exc))
        model = None
    st.divider()
    st.caption(f"Transaction log: `{DEFAULT_LOG}`")
    st.caption("Supports PDF, TXT, MD and PY. Reads up to 25 MB per file and sends at most 4,500 content characters to local Ollama.")

st.subheader("1 · Choose a folder")
if "folder_path" not in st.session_state:
    st.session_state.folder_path = str(Path("sample_files").resolve())
path_column, browse_column = st.columns([5, 1], vertical_alignment="bottom")
with browse_column:
    if st.button("Browse…", width="stretch"):
        root = None
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askdirectory(parent=root, mustexist=True)
            if chosen:
                st.session_state.folder_path = chosen
        except Exception as exc:
            st.warning(f"Folder picker unavailable: {exc}. Enter a path instead.")
        finally:
            if root is not None:
                root.destroy()
with path_column:
    folder_text = st.text_input("Folder path", key="folder_path",
                                help="A folder on the computer running Streamlit.")
recursive = st.checkbox("Include nested folders", value=False)

if st.button("Scan and suggest names", type="primary", disabled=model is None):
    st.session_state.pop("rename_editor", None)
    st.session_state.pop("last_batch", None)
    try:
        files = scan(Path(folder_text), recursive)
        if not files:
            st.info("No supported files found in this folder.")
            st.session_state.rows = []
        else:
            rows = []
            progress = st.progress(0, text="Reading files and asking the local model…")
            for index, path in enumerate(files):
                row = {"Select": False, "Folder": str(path.parent), "Original": path.name,
                       "Suggested": path.name, "Status": "Ready", "source": str(path),
                       "size": 0, "mtime_ns": 0}
                try:
                    stat = path.stat()
                    row["size"], row["mtime_ns"] = stat.st_size, stat.st_mtime_ns
                    row["Suggested"] = suggest_name(extract_content(path), model, path.suffix)
                    row["Select"] = row["Suggested"] != path.name
                except (RenameError, OSError) as exc:
                    row["Status"] = str(exc)
                rows.append(row)
                progress.progress((index + 1) / len(files), text=f"Processed {index + 1} of {len(files)}")
            progress.empty()
            st.session_state.rows = rows
    except RenameError as exc:
        st.error(str(exc))

rows = st.session_state.get("rows", [])
if rows:
    st.subheader("2 · Review the preview")
    st.caption("Edit Suggested, deselect any row, and review the folder path. Files with extraction errors stay unselected.")
    display_rows = [{key: row[key] for key in ("Select", "Folder", "Original", "Suggested", "Status")} for row in rows]
    edited = st.data_editor(display_rows, key="rename_editor", hide_index=True, width="stretch",
                            disabled=["Folder", "Original", "Status"], num_rows="fixed",
                            column_config={"Select": st.column_config.CheckboxColumn(width="small"),
                                           "Suggested": st.column_config.TextColumn(width="large")})
    selected = []
    edited_rows = edited if isinstance(edited, list) else edited.to_dict("records")
    for original, item in zip(rows, edited_rows):
        if item["Select"] and original["Status"] == "Ready":
            selected.append({"source": original["source"], "target_name": item["Suggested"],
                             "size": original["size"], "mtime_ns": original["mtime_ns"]})
    count = sum(row["target_name"] != Path(row["source"]).name for row in selected)
    a, b = st.columns(2)
    a.metric("Selected changes", count)
    b.metric("Potential manual time saved", f"{count * 30 // 60}m {count * 30 % 60}s",
             help="Illustrative estimate: 30 seconds of manual reading and naming per file. This is not measured performance.")
    confirm = st.checkbox("I reviewed these names and confirm the selected renames")
    if st.button("Rename selected files", type="primary", disabled=not confirm or count == 0):
        try:
            batch = apply_batch(selected)
            st.session_state.last_batch = batch
            st.session_state.rows = []
            st.rerun()
        except RenameError as exc:
            st.error(str(exc))

if st.session_state.get("last_batch"):
    batch = st.session_state.last_batch
    st.success(f"Renamed {len(batch['moves'])} file(s). Batch {batch['id'][:8]} saved to the transaction log.")
    st.subheader("Before → after")
    st.dataframe([{"Folder": str(Path(move["source"]).parent),
                   "Before": Path(move["source"]).name,
                   "After": Path(move["target"]).name} for move in batch["moves"]],
                 hide_index=True, width="stretch")
    st.caption(f"Potential manual time saved: {len(batch['moves']) * 30} seconds at an assumed 30 seconds per file.")

st.divider()
st.subheader("Undo")
try:
    undoable = latest_undoable()
    if undoable:
        st.caption(f"Most recent batch: {undoable['id'][:8]} · {undoable['created_at']}")
        if st.button("Undo most recent rename batch"):
            try:
                undone = undo_latest()
                st.session_state.pop("last_batch", None)
                st.success(f"Undid batch {undone['id'][:8]}.")
                st.rerun()
            except RenameError as exc:
                st.error(str(exc))
    else:
        st.caption("No batch available to undo.")
except RenameError as exc:
    st.error(str(exc))
