import os, re, sys, shutil, subprocess, threading, pathlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
import core

ALL = "All folders"

def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Knowledge Search")
        try:
            self.iconbitmap(resource_path("logo.ico"))
        except Exception:
            pass
        self.geometry("1200x900")
        self.minsize(900, 650)
        self.pages = []          # sources shown in the list
        self.last_q = ""
        self.stop = threading.Event()
        self.indexing = False
        self.fs = 12             # base font size (A- / A+ change it)
        self.setup_style()
        self.build()
        self.bind("<Control-plus>", lambda e: self.zoom(1))
        self.bind("<Control-equal>", lambda e: self.zoom(1))
        self.bind("<Control-minus>", lambda e: self.zoom(-1))
        self.refresh_library()

    # ----- look -----
    def setup_style(self):
        self.f_text = tkfont.Font(family="Segoe UI", size=self.fs)
        self.f_bold = tkfont.Font(family="Segoe UI", size=self.fs, weight="bold")
        self.f_small = tkfont.Font(family="Segoe UI", size=max(9, self.fs - 2))
        self.f_ask = tkfont.Font(family="Segoe UI", size=self.fs + 2)
        st = ttk.Style(self)
        try:
            st.theme_use("vista")
        except Exception:
            st.theme_use("clam")
        st.configure("TButton", font=self.f_text, padding=(14, 7))
        st.configure("Accent.TButton", font=self.f_bold, padding=(22, 8))
        st.configure("TLabel", font=self.f_text)
        st.configure("TCheckbutton", font=self.f_text)
        st.configure("Head.TLabel", font=self.f_bold)
        st.configure("Small.TLabel", font=self.f_small)
        st.configure("TCombobox", padding=6)
        self.option_add("*TCombobox*Listbox.font", self.f_text)

    def zoom(self, step):
        self.fs = max(9, min(22, self.fs + step))
        for f in (self.f_text, self.f_bold):
            f.configure(size=self.fs)
        self.f_small.configure(size=max(9, self.fs - 2))
        self.f_ask.configure(size=self.fs + 2)

    def build(self):
        # --- top bar ---
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14, pady=(14, 6))
        self.b_folder = ttk.Button(bar, text="Add PDF folder...", command=self.add_folder)
        self.b_files = ttk.Button(bar, text="Add PDF files...", command=self.add_files)
        self.b_folder.pack(side="left")
        self.b_files.pack(side="left", padx=8)
        ttk.Button(bar, text="Library...", command=self.manage).pack(side="left")
        ttk.Button(bar, text="Settings", command=self.settings).pack(side="left", padx=8)
        self.lib = tk.StringVar()
        ttk.Label(bar, textvariable=self.lib, style="Head.TLabel").pack(side="left", padx=14)
        ttk.Button(bar, text="A+", width=4, command=lambda: self.zoom(1)).pack(side="right")
        ttk.Button(bar, text="A-", width=4, command=lambda: self.zoom(-1)).pack(side="right", padx=6)

        # --- progress ---
        prog = ttk.Frame(self)
        prog.pack(fill="x", padx=14)
        self.pbar = ttk.Progressbar(prog, mode="determinate")
        self.pbar.pack(side="left", fill="x", expand=True, ipady=2)
        self.b_cancel = ttk.Button(prog, text="Cancel", command=self.stop.set, state="disabled")
        self.b_cancel.pack(side="right", padx=(8, 0))
        self.status = tk.StringVar()
        self.status_lbl = ttk.Label(self, textvariable=self.status, foreground="#555",
                                    style="Small.TLabel", justify="left")
        self.status_lbl.pack(fill="x", padx=14, pady=(4, 8))
        self.status_lbl.bind("<Configure>",
                             lambda e: self.status_lbl.config(wraplength=max(300, e.width - 10)))

        # --- question row ---
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14)
        self.q = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.q, font=self.f_ask)
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        entry.bind("<Return>", lambda e: self.ask())
        entry.focus()
        self.grp = tk.StringVar(value=ALL)
        self.grp_box = ttk.Combobox(top, textvariable=self.grp, values=[ALL], width=26,
                                    state="readonly", font=self.f_text)
        self.grp_box.pack(side="left", padx=8)
        self.btn = ttk.Button(top, text="Ask", style="Accent.TButton", command=self.ask)
        self.btn.pack(side="left")

        # --- footer first (so it never gets pushed off screen) ---
        ttk.Label(self, text="AI answers can be wrong. Always verify against the original page.",
                  foreground="#a00", style="Small.TLabel").pack(side="bottom", anchor="w",
                                                                padx=14, pady=(2, 10))

        # --- three resizable panes ---
        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True, padx=14, pady=(10, 0))

        self.answer = self.text_pane(panes, "Answer", weight=2, height=7)
        self.src = self.list_pane(panes)
        self.preview = self.text_pane(panes, "Page text (your words are highlighted)",
                                      weight=4, height=12)
        self.preview.tag_configure("hit", background="#fff2a8")
        self.answer.tag_configure("label_in", foreground="#0a6b2d", font=self.f_bold)
        self.answer.tag_configure("label_out", foreground="#b3261e", font=self.f_bold)

    def text_pane(self, panes, title, weight, height):
        frame = ttk.Frame(panes)
        ttk.Label(frame, text=title, style="Head.TLabel").pack(anchor="w", pady=(6, 3))
        inner = ttk.Frame(frame)
        inner.pack(fill="both", expand=True)
        txt = tk.Text(inner, wrap="word", font=self.f_text, height=height, padx=10, pady=8,
                      relief="solid", borderwidth=1, spacing2=3, spacing3=6)
        sb = ttk.Scrollbar(inner, orient="vertical", command=txt.yview)
        txt.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        panes.add(frame, weight=weight)
        return txt

    def list_pane(self, panes):
        frame = ttk.Frame(panes)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(6, 3))
        self.src_title = tk.StringVar(value="Sources (double-click to open the PDF at that page)")
        ttk.Label(row, textvariable=self.src_title, style="Head.TLabel").pack(side="left")
        ttk.Button(row, text="Open PDF at page", command=self.open_pdf).pack(side="right")
        inner = ttk.Frame(frame)
        inner.pack(fill="both", expand=True)
        lb = tk.Listbox(inner, font=self.f_text, height=7, exportselection=False,
                        activestyle="none", relief="solid", borderwidth=1,
                        selectbackground="#2f6fbd", selectforeground="white")
        sb = ttk.Scrollbar(inner, orient="vertical", command=lb.yview)
        sbx = ttk.Scrollbar(frame, orient="horizontal", command=lb.xview)
        lb.config(yscrollcommand=sb.set, xscrollcommand=sbx.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        sbx.pack(fill="x")
        lb.bind("<<ListboxSelect>>", self.preview_page)
        lb.bind("<Double-Button-1>", lambda e: self.open_pdf())
        panes.add(frame, weight=2)
        return lb

    # ----- helpers -----
    def set_text(self, widget, text):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def set_answer(self, label, kind, body):
        """label = bold first line (green = in documents, red = not in documents)."""
        self.answer.delete("1.0", "end")
        if label:
            self.answer.insert("end", label + "\n", "label_" + kind)
        self.answer.insert("end", body)

    def refresh_library(self):
        n, p, groups = core.stats()
        self.lib.set("Library: %d PDFs, %d pages" % (n, p))
        self.grp_box.config(values=[ALL] + groups)
        if self.grp.get() not in [ALL] + groups:
            self.grp.set(ALL)
        if n == 0 and not self.indexing:
            self.status.set("Click 'Add PDF folder...' to begin.")

    def highlight(self):
        self.preview.tag_remove("hit", "1.0", "end")
        words = {w for w in re.findall(r"[A-Za-z0-9]+", self.last_q.lower())
                 if w not in core.STOP and len(w) > 2}
        for w in words:
            start = "1.0"
            while True:
                pos = self.preview.search(w, start, stopindex="end", nocase=True)
                if not pos:
                    break
                end = "%s+%dc" % (pos, len(w))
                self.preview.tag_add("hit", pos, end)
                start = end

    # ----- adding PDFs -----
    def add_folder(self):
        root = filedialog.askdirectory(title="Choose the folder that contains your PDFs")
        if not root:
            return
        items = core.items_from_folder(root)
        if not items:
            messagebox.showinfo("No PDFs", "No PDF files were found in that folder.")
            return
        self.start_index(items)

    def add_files(self):
        files = filedialog.askopenfilenames(title="Choose PDF files",
                                            filetypes=[("PDF files", "*.pdf")])
        if files:
            self.start_index(core.items_from_files(files))

    def start_index(self, items):
        if self.indexing:
            return
        self.indexing = True
        self.stop.clear()
        for b in (self.b_folder, self.b_files):
            b.config(state="disabled")
        self.b_cancel.config(state="normal")
        self.pbar.config(maximum=len(items), value=0)
        threading.Thread(target=self.index_worker, args=(items,), daemon=True).start()

    def index_worker(self, items):
        def progress(done, total, name):
            self.after(0, self.on_progress, done, total, name)
        try:
            done, failed = core.index_items(items, progress, self.stop)
            self.after(0, self.on_index_done, done, len(items), failed)
        except Exception as e:
            self.after(0, self.on_index_done, 0, len(items), [("(indexing)", str(e))])

    def on_progress(self, done, total, name):
        self.pbar.config(value=done)
        if name:
            self.status.set("Reading PDF %d of %d: %s" % (done + 1, total, name))

    def on_index_done(self, done, total, failed):
        self.indexing = False
        for b in (self.b_folder, self.b_files):
            b.config(state="normal")
        self.b_cancel.config(state="disabled")
        self.refresh_library()
        if self.stop.is_set():
            self.status.set("Stopped. %d of %d PDFs are ready. Adding the same folder again continues." % (done, total))
        else:
            self.status.set("Finished. %d of %d PDFs are ready to search." % (done, total))
        if failed:
            messagebox.showwarning("Some files were skipped",
                                   "\n".join("%s: %s" % f for f in failed[:15]))

    # ----- library manager -----
    def manage(self):
        if self.indexing:
            messagebox.showinfo("Busy", "Wait until reading the PDFs is finished.")
            return
        win = tk.Toplevel(self)
        win.title("Library")
        win.geometry("980x580")
        win.minsize(700, 400)
        win.transient(self)
        info = tk.StringVar()
        ttk.Label(win, textvariable=info, wraplength=920).pack(anchor="w", padx=14, pady=10)

        row = ttk.Frame(win)
        row.pack(side="bottom", fill="x", padx=14, pady=12)

        box = ttk.Frame(win)
        box.pack(fill="both", expand=True, padx=14)
        lb = tk.Listbox(box, selectmode="extended", font=self.f_small, activestyle="none",
                        relief="solid", borderwidth=1)
        sb = ttk.Scrollbar(box, orient="vertical", command=lb.yview)
        sbx = ttk.Scrollbar(win, orient="horizontal", command=lb.xview)
        lb.config(yscrollcommand=sb.set, xscrollcommand=sbx.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        sbx.pack(fill="x", padx=14)
        files = []

        def load():
            nonlocal files
            files = core.list_files()
            lb.delete(0, "end")
            for path, grp, pages in files:
                tag = "" if os.path.exists(path) else "   [FILE MISSING]"
                lb.insert("end", "%s  |  %s  |  %d pages%s" % (grp, path, pages, tag))
            n, p, _ = core.stats()
            mb = os.path.getsize(core.DB_FILE) / 1e6 if os.path.exists(core.DB_FILE) else 0
            info.set("%d PDFs, %d pages. The app stores only the extracted text (%.0f MB), "
                     "not copies of your PDFs." % (n, p, mb))
            self.refresh_library()

        def remove_selected():
            sel = [files[i][0] for i in lb.curselection()]
            if sel and messagebox.askyesno("Remove", "Remove %d file(s) from the library? "
                                           "Your PDFs are not deleted." % len(sel), parent=win):
                core.remove_files(sel)
                load()

        def dedupe():
            self.status.set("Checking for duplicates...")
            win.update_idletasks()
            n = core.remove_duplicates()
            self.status.set("Removed %d duplicate(s)." % n)
            load()

        def clear():
            if messagebox.askyesno("Clear library", "Remove EVERYTHING from the library? "
                                   "Your PDFs are not deleted; you can add them again.", parent=win):
                core.clear_library()
                load()

        ttk.Button(row, text="Remove selected", command=remove_selected).pack(side="left")
        ttk.Button(row, text="Remove duplicates", command=dedupe).pack(side="left", padx=8)
        ttk.Button(row, text="Clear everything", command=clear).pack(side="right")
        load()

    # ----- settings -----
    def settings(self):
        s = core.load_settings()
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("700x560")
        win.minsize(600, 520)
        win.transient(self)
        ttk.Label(win, text="Gemini API key (optional, enables AI answers)",
                  style="Head.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
        key = tk.StringVar(value=s["gemini_api_key"])
        ttk.Entry(win, textvariable=key, show="*", font=self.f_text).pack(fill="x", padx=16, ipady=4)
        ttk.Label(win, text="Model", style="Head.TLabel").pack(anchor="w", padx=16, pady=(14, 4))
        model = tk.StringVar(value=s["model"])
        ttk.Entry(win, textvariable=model, width=40, font=self.f_text).pack(anchor="w", padx=16, ipady=4)
        ttk.Label(win, text="What kind of documents are these? (helps the AI choose search phrases)",
                  style="Head.TLabel").pack(anchor="w", padx=16, pady=(14, 4))
        coll = tk.StringVar(value=s["collection"])
        ttk.Entry(win, textvariable=coll, font=self.f_text).pack(fill="x", padx=16, ipady=4)
        general = tk.BooleanVar(value=bool(s.get("general_fallback", True)))
        ttk.Checkbutton(win, variable=general, text=(
            "If my documents do not answer the question, let Gemini answer from general "
            "knowledge (clearly labelled)")).pack(anchor="w", padx=16, pady=(14, 0))
        ttk.Label(win, wraplength=640, foreground="#555", style="Small.TLabel", text=(
            "Without a key the app works fully offline as a plain keyword search. With a key, "
            "your question and a few short excerpts of the best-matching pages are sent to "
            "Google Gemini. The PDF files themselves are never uploaded. If the general-answer "
            "option is on and your documents do not answer the question, only your question is "
            "sent. On Google's free tier, such data may be used to improve Google's "
            "products.")).pack(anchor="w", padx=16, pady=14)

        def save():
            core.save_settings({"gemini_api_key": key.get().strip(),
                                "model": model.get().strip() or "gemini-flash-latest",
                                "collection": coll.get().strip() or "PDF documents",
                                "general_fallback": bool(general.get())})
            win.destroy()
        ttk.Button(win, text="Save", style="Accent.TButton", command=save).pack(pady=8)

    # ----- asking -----
    def ask(self):
        q = self.q.get().strip()
        if not q:
            return
        if core.stats()[0] == 0:
            messagebox.showinfo("No documents yet", "Add a PDF folder or PDF files first.")
            return
        grp = None if self.grp.get() == ALL else self.grp.get()
        self.last_q = q
        self.btn.config(state="disabled")
        self.status.set("Searching... (a new question can take 10 to 20 seconds with AI on)")
        self.set_text(self.answer, "")
        self.set_text(self.preview, "")
        self.src.delete(0, "end")
        self.pages = []
        self.src_title.set("Sources (double-click to open the PDF at that page)")
        threading.Thread(target=self.worker, args=(q, grp), daemon=True).start()

    def worker(self, q, grp):
        try:
            # Step 1: instant results from the local database (no waiting for Gemini)
            cached = core.cached_phrases(q)
            phrases, results = core.smart_search(q, grp=grp, phrases=cached)
            sources = core.make_sources(results)
            if not core.ai_enabled():
                self.after(0, self.show, None, "", sources, [], phrases, None)
                return
            if sources:
                self.after(0, self.show_quick, sources)
            # Step 2: AI phrases (only if new) and the AI answer from the documents
            if not cached:
                phrases, results = core.smart_search(q, grp=grp)
                sources = core.make_sources(results)
            used, verdict, text = [], None, ""
            if sources:
                for rnd in range(2):
                    batch = core.pick_pages(results, skip=rnd * core.AI_PAGES)
                    if not batch:
                        break
                    v, t = core.write_answer(q, batch)
                    if v in ("DIRECT", "RELATED"):
                        used, verdict, text = batch, v, t
                        break
                    if v == "NONE":
                        verdict = "NONE"
                    else:
                        break                    # the AI failed; do not keep retrying
            # Step 3: documents do not answer -> clearly labelled general answer
            general = None
            if (verdict == "NONE" or not sources) \
                    and core.load_settings().get("general_fallback", True):
                general = core.general_answer(q)
            self.after(0, self.show, verdict, text, sources, used, phrases, general)
        except Exception as e:
            self.after(0, self.fail, str(e))

    def show_quick(self, sources):
        self.pages = sources
        self.src.delete(0, "end")
        self.set_answer("", "in", "Matching pages are listed below. "
                                  "The AI is still checking them for a direct answer...")
        for i, p in enumerate(sources, 1):
            self.src.insert("end", "[%d]  %s  |  %s  |  PDF page %d" % (i, p["file"], p["grp"], p["page"]))
        self.src_title.set("Sources: %d pages (AI still checking...)" % len(sources))
        self.src.selection_set(0)
        self.preview_page()
        self.status.set("Showing keyword matches. Waiting for the AI answer...")

    def show(self, verdict, text, sources, used, phrases, general=None):
        self.btn.config(state="normal")
        self.src.delete(0, "end")
        self.pages = []
        if not sources and not general:
            self.set_answer("", "in", "Not found in the documents.")
            self.src_title.set("Sources (none)")
            self.status.set("Done. " + core.AI_STATE["error"] if core.AI_STATE["error"] else "Done.")
            return

        shown = sources
        label, kind = "", "in"
        if verdict == "DIRECT":
            label, kind, msg = "THIS TOPIC IS IN YOUR DOCUMENTS", "in", text
        elif verdict == "RELATED":
            label, kind = "THIS TOPIC IS IN YOUR DOCUMENTS (not stated directly)", "in"
            msg = "The excerpts do not state this directly, but they discuss:\n" + text
        elif verdict == "NONE" or (not sources and general):
            # Keep ALL the pages that matched, best first, so the user can check the AI.
            shown = ([s for s in sources if s["strong"]]
                     + [s for s in sources if not s["strong"]])
            if general:
                label, kind = "YOUR DOCUMENTS DO NOT ANSWER THIS QUESTION", "out"
                msg = ("The answer below comes from Gemini's general knowledge, NOT from your "
                       "PDFs. It can be wrong. Please verify it elsewhere.\n\n" + general)
                if shown:
                    msg += ("\n\nThe pages listed below matched some of your words, but the AI "
                            "found no answer in them. They are NOT confirmed as relevant. If "
                            "you think the AI is wrong, read them yourself.")
            elif shown:
                msg = ("The AI could not confirm an answer from the documents.\n"
                       "The pages below match your words, but they are NOT confirmed "
                       "as an answer. Please read them yourself.")
            else:
                msg = "Not found in the documents."
        elif not core.ai_enabled():
            msg = ("AI answers are off (no Gemini key in Settings). "
                   "The matching pages are listed below.")
        else:
            msg = ("The AI answer is unavailable right now (%s). "
                   "The matching pages are listed below." % core.AI_STATE["error"])
        self.set_answer(label, kind, msg)

        # Pages the AI read go first, in the same order, so [1], [2] in the answer
        # match rows 1, 2 in the list.
        if verdict in ("DIRECT", "RELATED"):
            by_key = {(s["path"], s["page"]): s for s in shown}
            first = [by_key[(u["path"], u["page"])] for u in used
                     if (u["path"], u["page"]) in by_key]
            ids = {(s["path"], s["page"]) for s in first}
            shown = first + [s for s in shown if (s["path"], s["page"]) not in ids]

        self.pages = shown
        for i, p in enumerate(shown, 1):
            self.src.insert("end", "[%d]  %s  |  %s  |  PDF page %d" % (i, p["file"], p["grp"], p["page"]))
        if shown:
            if verdict == "NONE":
                self.src_title.set("Sources: %d pages that match your words (NOT confirmed as an answer)"
                                   % len(shown))
            else:
                self.src_title.set("Sources: %d pages (double-click to open the PDF at that page)"
                                   % len(shown))
            self.src.selection_set(0)
            self.preview_page()
        else:
            self.src_title.set("Sources (none)")
        self.status.set(("Searched for: " + ", ".join(phrases)) if phrases else "Done.")

    def fail(self, msg):
        self.btn.config(state="normal")
        self.status.set("Error: " + msg)

    def selected(self):
        sel = self.src.curselection()
        return self.pages[sel[0]] if sel else None

    def preview_page(self, event=None):
        p = self.selected()
        if p:
            self.set_text(self.preview, core.page_text(p["path"], p["page"]))
            self.highlight()

    def open_pdf(self):
        p = self.selected()
        if not p:
            self.status.set("Click a source first.")
            return
        path, page = p["path"], p["page"]
        if not os.path.exists(path):
            self.status.set("The PDF was not found. It may have been moved or deleted.")
            return
        url = pathlib.Path(path).as_uri() + "#page=%d" % page

        def find(candidates, names):
            for c in candidates:
                if os.path.exists(c):
                    return c
            for n in names:
                w = shutil.which(n)
                if w:
                    return w
            return None

        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")

        edge = find([pf86 + r"\Microsoft\Edge\Application\msedge.exe",
                     pf + r"\Microsoft\Edge\Application\msedge.exe"], ["msedge"])
        chrome = find([pf + r"\Google\Chrome\Application\chrome.exe",
                       pf86 + r"\Google\Chrome\Application\chrome.exe",
                       local + r"\Google\Chrome\Application\chrome.exe"], ["chrome"])
        acrobat = find([pf + r"\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
                        pf86 + r"\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                        pf + r"\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"], [])
        try:
            if edge:
                subprocess.Popen([edge, url])
            elif chrome:
                subprocess.Popen([chrome, url])
            elif acrobat:
                subprocess.Popen([acrobat, "/A", "page=%d" % page, path])
            else:
                raise FileNotFoundError
            self.status.set("Opened %s at page %d." % (p["file"], page))
        except Exception:
            os.startfile(path)                       # default app, cannot jump to a page
            self.clipboard_clear()
            self.clipboard_append(str(page))
            self.status.set("Opened the PDF. Go to PDF page %d (the number is copied)." % page)

App().mainloop()



# pyinstaller --noconfirm --windowed --name "PDF Knowledge Search" --icon logo.ico --add-data "logo.ico;." gui.py