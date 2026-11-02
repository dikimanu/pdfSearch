# PDF Knowledge Search

A free Windows desktop app that lets you search a large library of PDFs (for example, Supreme Court Reports) and ask questions in plain language. It works fully offline as a fast keyword search, and can optionally use Google Gemini to suggest better search phrases and write short, source-cited answers.

Built with Python, Tkinter, SQLite FTS5 and PyMuPDF.

---

## Features

- **Fast full-text search** across thousands of PDFs, page by page
- **Works offline**: no internet or API key needed for keyword search
- **Optional AI answers** (Gemini): short answers with citations like [1], [2] that point to the pages listed below
- **Honest labels**: every answer is marked as in your documents, related, or not in your documents
- **Open the PDF at the exact page** (Edge, Chrome or Adobe Reader)
- **Folder filter**: search all folders or just one
- **Duplicate detection**: identical PDFs are skipped automatically
- **Resumable indexing**: stop at any time and add the same folder again to continue
- **Adjustable text size**: A+ / A- buttons, or Ctrl + / Ctrl -

---

## Installation

### Option 1: Installer
Run `PDF-Knowledge-Search-Setup-v1.2.exe` and follow the wizard. No admin rights are needed.

### Option 2: Run from source
```
pip install pymupdf
python gui.py
```
Requires Python 3.9 or newer on Windows. `core.py` and `gui.py` must be in the same folder.

---

## How to use

### 1. Add your PDFs
- Click **Add PDF folder...** to index a whole folder, including sub-folders. The first-level sub-folder name becomes the "folder" you can filter by.
- Or click **Add PDF files...** to pick individual files.
- Watch the progress bar. You can click **Cancel** at any time; adding the same folder again continues where it stopped.
- Files that are already indexed and unchanged are skipped, so re-adding a folder is quick.

The app stores only the extracted text, not copies of your PDFs. Keep your PDFs where they are, because the app needs the original files to open a page.

### 2. Ask a question
- Type a question or keywords in the box and press **Enter** or click **Ask**.
- Use the dropdown beside the box to search only one folder.

### 3. Read the results
The window has three panes:

| Pane | What it shows |
|---|---|
| **Answer** | The AI answer (if enabled) or a note about the results |
| **Sources** | Matching pages, best first, up to 300 |
| **Page text** | The full text of the selected page, with your words highlighted |

Click a source to preview it. **Double-click** it, or click **Open PDF at page**, to open the original PDF at that page.

### 4. Understand the answer labels (AI on)
- **THIS TOPIC IS IN YOUR DOCUMENTS**: the pages directly answer the question.
- **THIS TOPIC IS IN YOUR DOCUMENTS (not stated directly)**: the pages discuss the topic but do not state exactly what you asked.
- **YOUR DOCUMENTS DO NOT ANSWER THIS QUESTION**: the AI found nothing in the pages. If "general answer" is enabled, a clearly labelled answer from Gemini's general knowledge is shown. This is **not** from your PDFs.

Numbers like [1] in an answer match the numbered rows in the Sources list.

### 5. Manage the library
Click **Library...** to:
- see every indexed file and spot any marked `[FILE MISSING]`
- **Remove selected** files from the index (your PDFs are not deleted)
- **Remove duplicates**
- **Clear everything**

---

## Turning on AI (optional)

1. Get a free API key from Google AI Studio.
2. Click **Settings** and paste the key.
3. Set **Model** (default `gemini-flash-latest`).
4. In "What kind of documents are these?", describe your collection (for example, "Indian Supreme Court judgments"). This helps the AI choose better search phrases.
5. Choose whether Gemini may answer from general knowledge when your documents do not answer the question.
6. Click **Save**.

What happens when you ask a question with AI on:
1. Local keyword results appear immediately.
2. Gemini converts your question into 5 to 8 search phrases (saved, so repeated questions are instant).
3. The best-matching pages are sent to Gemini, which answers using only those pages.

---

## Where your data is stored

Everything lives in `%APPDATA%\PDFSearch`:

| File | Purpose |
|---|---|
| `library.db` | The search index (extracted text) |
| `settings.json` | Your settings, including the API key |
| `phrase_cache.json` | Saved AI search phrases |

Uninstalling the app does not delete this folder, so your library survives upgrades. Delete the folder to remove all data.

---

## Limitations

**Please read these before relying on the results.**

### Accuracy
- **AI answers can be wrong.** Always check the original page before using an answer, especially for legal, medical or academic work.
- **This is not legal advice.** The "general knowledge" answers are not from your documents and may be inaccurate or incomplete.
- The AI reads only the **top 16 pages** (two batches of 8, each page cut to about 3,000 characters). If the answer is on a page that ranked lower, or lies past the cut-off on a long page, the AI can wrongly say "not in your documents". The Sources list still shows all matching pages, so check it yourself.
- A "not in your documents" verdict needs two models to agree. If Gemini errors out or the quota is used up, you only get the keyword results.

### Search
- Search is **keyword based**, not meaning based. It uses word stemming (so "running" matches "run") but cannot find a page that expresses the idea in completely different words unless the AI suggests the right phrase.
- Only **English letters and digits** (A-Z, 0-9) are used in queries. Words in other scripts, such as Hindi or Bengali, and punctuation-heavy terms like section symbols are ignored.
- Common words (such as "the", "of", "should") are ignored in your question.
- Results are at **page level**. The app does not locate the exact paragraph in the PDF.
- Page text is cleaned for law reports: lone letters A to H on their own line (margin markers) are removed. This is helpful for Supreme Court Reports but may strip a genuine single-letter line in other documents.

### PDFs
- **No OCR.** Scanned or image-only PDFs have no extractable text and will be indexed with no searchable pages. Run OCR on them first (for example with Adobe Acrobat or OCRmyPDF).
- **Password-protected PDFs** are skipped and reported as failed.
- Tables, columns and footnotes may be extracted in an odd reading order, which can affect snippets and AI answers.
- Identical files (same content) are indexed only once; the later copy is skipped.
- If you edit or replace a PDF, add it again to re-index it. The app does not watch folders for changes.
- If you move or delete a PDF, it stays in the index (marked `[FILE MISSING]` in Library...) until you remove it, and it cannot be opened.

### Platform
- **Windows only.** Folder paths, `%APPDATA%`, and the PDF-opening logic are Windows specific.
- "Open at page" works with **Microsoft Edge, Google Chrome or Adobe Acrobat/Reader**. With any other PDF viewer the file opens on page 1 and the page number is copied to your clipboard.
- Very large libraries make the first indexing slow, and the index file grows with the amount of text.

### Privacy and cost
- With AI **off**, nothing leaves your computer.
- With AI **on**, your question and short excerpts of the best-matching pages are sent to Google Gemini. The PDF files themselves are never uploaded.
- If the general-answer option is on and your documents do not answer, your question alone is sent to Gemini.
- On Google's free tier, submitted data may be used to improve Google's products. Do not use AI mode with confidential documents.
- The free tier has rate and daily limits. Model names also change over time; if a model stops working, update the **Model** field in Settings.
- Your API key is stored as plain text in `settings.json` on your computer.

---

## Troubleshooting

| Problem | What to try |
|---|---|
| "The AI answer is unavailable right now" | Check your API key, internet connection and model name in Settings. The message shows Google's error code. |
| A PDF was skipped | Open it: it may be password protected, corrupted, or a duplicate of another file. |
| No results for a scanned PDF | The PDF has no text layer. OCR it first. |
| Page does not open at the right page | Install Edge, Chrome or Adobe Reader, or use the page number copied to the clipboard. |
| Library shows `[FILE MISSING]` | Restore the file or remove it from the library. |
| The text is too small | Use A+ or Ctrl and + . |

---

## Building from source

Create the executable:
```
pyinstaller --noconfirm --windowed --name "PDF Knowledge Search" --icon logo.ico --add-data "logo.ico;." gui.py
```

Then compile the installer script with Inno Setup (6.3 or newer). The output is saved in `installer_output`.

---

## Author

Satyabrata Pal
