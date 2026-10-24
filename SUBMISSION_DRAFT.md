# LazyRename: I let a local model read my messy files before naming them

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

I keep ending up with files named `document_001.txt`, `notes_final_v3.md`, and `scan0004.pdf`. Renaming one is easy. Renaming a whole folder means opening each file, figuring out what it is, and checking that the new name will not collide with something already there. I tend to put it off.

LazyRename does the reading. It scans a local folder for PDF, TXT, MD, and PY files, then asks an installed Ollama model for a short filename based on each file's contents. I get a table with the old and suggested names, and I can edit or deselect any row. The rename button stays unavailable until I check a confirmation box.

It keeps each file in its original folder and preserves its extension. It also checks Windows filename rules and collisions, writes a JSON transaction log, and offers an undo button for the latest batch. The code never executes a scanned Python file.

## Demo

**Video:** [Add the 60-second screen recording before publishing. The shot list is in `DEMO.md` in the repository.]

Here is one result from a local test using `qwen3.5:4b` and the included sample files:

| Before | Suggested name |
| --- | --- |
| `scan0004.pdf` | `quarterly-accessibility-audit-checkout-forms-labels-focus.pdf` |

That PDF contains a short note about checkout form labels and keyboard focus. The model did not receive `scan0004.pdf` in its prompt. In the same disposable-folder test, four suggestions were confirmed and renamed, then Undo restored every original name. The exact words a model suggests can vary by model and run.

This is a local desktop workflow, so there is no hosted app link. To try it, copy `sample_files` to a disposable folder, follow the [Windows setup instructions](https://github.com/ABhattacharya-dev/LazyRename#readme), select that folder in LazyRename, and choose an installed Ollama model.

## Code

[LazyRename on GitHub](https://github.com/ABhattacharya-dev/LazyRename) is MIT licensed. The main pieces are the [Streamlit interface](https://github.com/ABhattacharya-dev/LazyRename/blob/main/app.py), [file handling and undo logic](https://github.com/ABhattacharya-dev/LazyRename/blob/main/lazyrename/core.py), and [Ollama client](https://github.com/ABhattacharya-dev/LazyRename/blob/main/lazyrename/ollama.py). The repository also has sample files and tests for filename validation, collisions, encrypted PDFs, interrupted batches, and undo.

## How I Built It

The app uses Python 3.11+, Streamlit for the review screen, PyMuPDF for PDF text extraction, and Ollama's local API for suggestions. The user can pick from models already installed in Ollama. In my test I used `qwen3.5:4b`; the setup guide also shows how to install `gemma3:4b`.

The model gets a bounded excerpt of the file's contents, with no original filename in the prompt. LazyRename reads up to three PDF pages or 64 KB of a text file and sends no more than 4,500 characters to Ollama. It skips empty files, encrypted PDFs, binary files, and files over 25 MB. Those limits keep a stray large file from turning a quick folder cleanup into a huge inference job.

After inference, Python sanitizes the proposed name and keeps the original extension. Before applying a batch, it checks for collisions and verifies that the source files have not changed since the preview. The transaction log records the moves so Undo can check the paths again before restoring them. If the original name is occupied or a renamed file has changed, Undo stops instead of overwriting it.

The model can still misunderstand a file, especially when useful details fall outside the excerpt. That is why the preview is editable and every rename needs a deliberate confirmation. Image-only PDFs need OCR, which this version does not have.

## Why Does Open Innovation Matter?

These files can contain private notes, code, or work documents. With Ollama, the excerpt goes to a model running on the same computer, through `127.0.0.1`; it does not have to go to a paid hosted API. There is no API key, and I can switch models without rebuilding the app around one provider.

The source is open, too. Someone can inspect the extraction limits, change the prompt, add OCR, or tighten the rename checks. The app disables Streamlit usage stats and implements no telemetry. Packages and models need to be downloaded first; I have not tested a full run with network connectivity disabled, so I am not claiming an offline test result.

## My Agent Session

I used an AI coding assistant while building and testing LazyRename. I have not shared the session transcript yet. If I add it, I will review it first and link it here.

## The Lazy Payoff

LazyRename displays a potential saving of 30 seconds per selected file. In the four-file sample run, that showed **two minutes**. It is an assumption for illustrating the manual work, not a measured speedup. I have not timed the full process against hand-renaming a real folder, including model loading and reviewing suggestions.

The practical payoff I have verified is simpler: the app read four sample files, offered content-based names, applied the confirmed changes, and restored them with Undo. I can leave the final choice to myself without doing the first reading and naming pass by hand.
