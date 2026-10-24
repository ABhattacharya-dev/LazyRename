# LazyRename 🦥

LazyRename reads a small sample of each local PDF, TXT, Markdown, or Python file and asks an installed Ollama model for a meaningful filename. You review and edit every suggestion before anything moves. The app never uses a paid API, uploads content to a cloud service, or executes a scanned file.

Built for the [Hacktoberfest 2026 Open-Source AI Challenge, Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19).

## Windows setup

1. Install [Python 3.11 or newer](https://www.python.org/downloads/windows/) and [Ollama](https://ollama.com/download).
2. Open PowerShell in this project folder and install an instruct model:

   ```powershell
   ollama pull gemma3:4b
   ```

3. Create an environment and install dependencies:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   If your Python version is 3.12 or newer, replace `-3.11` with your installed version. If PowerShell blocks activation, run `.\.venv\Scripts\python.exe` directly in the commands below.

4. Start Ollama if it is not already running, then launch the app:

   ```powershell
   ollama serve
   # In a second PowerShell window:
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

5. Open the local URL Streamlit prints (usually `http://127.0.0.1:8501`). Select an installed model in the sidebar. Use **Browse…** or enter a folder path, choose whether to include nested folders, then click **Scan and suggest names**. The picker opens on the computer running Streamlit.

For a safe first run, copy `sample_files` to another folder and point LazyRename at the copy. A sample PDF is included along with text, Markdown, and Python examples.

## Workflow

1. The app scans only `.pdf`, `.txt`, `.md`, and `.py` files. Nested folders are optional. Symlinks are skipped.
2. It extracts at most three PDF pages or 64 KB of a text file, capped at 4,500 characters sent to local Ollama. Files above 25 MB, empty files, encrypted PDFs, binary files, and files without readable text show an error and remain unselected.
3. Ollama reads **content without the old filename** in its prompt. Its response becomes an editable suggestion. The original extension and folder are preserved.
4. Select the rows you want, edit suggestions, and check the confirmation box. The app checks invalid Windows characters, reserved names, collisions (including case-only conflicts), and source changes before renaming. It checks again during the batch and never intentionally replaces a destination.
5. See the before-and-after table. **Undo most recent rename batch** restores names if destinations still exist, original names are free, and renamed files have not changed.

If an operation is interrupted, completed moves remain recorded. Resolve any collision or changed-file warning before retrying undo. The JSON transaction log is stored at `%USERPROFILE%\.lazyrename\transactions.json`; it contains paths and file metadata, not file contents or model prompts. Keep a backup for valuable data, especially when testing on a new filesystem.

The time-saved display is an **illustrative estimate** of 30 seconds of manual reading and naming per selected file. It is not a measured benchmark.

## Privacy and limits

- The UI binds to `127.0.0.1`, Streamlit usage stats are disabled, and Ollama is called only at `127.0.0.1:11434`. No app telemetry is implemented.
- Models and Python packages must be downloaded before use. We have **not verified** operation with network connectivity disabled, so this project does not claim an offline test result.
- Image-only PDFs need OCR, which this MVP does not provide. Large files are skipped rather than partially processed. Content extraction favors the beginning of a file; relevant details later in a document may be missed.
- Model suggestions can be inaccurate. Inspect the preview. Undo cannot restore a file that was edited or moved outside the app after renaming.
- The app runs locally on your own computer. If you expose Streamlit or Ollama beyond localhost, that changes the privacy and access assumptions.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover sanitization, extension and reserved-name validation, existing and duplicate destinations, changed source files, binary/empty content, rename logging, and collision-safe undo.

## Project files

- `app.py`: Streamlit workflow and preview
- `lazyrename/core.py`: scanning, extraction, validation, rename transactions, undo
- `lazyrename/ollama.py`: local Ollama model list and inference
- `sample_files/`: disposable demo inputs
- `DEMO.md`: 60-second walkthrough
- `SUBMISSION_DRAFT.md`: DEV challenge post draft

MIT licensed; see [LICENSE](LICENSE).
