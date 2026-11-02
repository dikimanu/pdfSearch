import os, re, json, time, hashlib, sqlite3, urllib.request, urllib.error
from collections import defaultdict
from contextlib import closing
import pymupdf

# Each user's data lives in their own AppData folder (works for the .exe too)
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PDFSearch")
os.makedirs(APP_DIR, exist_ok=True)
DB_FILE = os.path.join(APP_DIR, "library.db")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
CACHE_FILE = os.path.join(APP_DIR, "phrase_cache.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    path TEXT PRIMARY KEY, grp TEXT, size INT, mtime REAL, pages INT, hash TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
    text, path UNINDEXED, file UNINDEXED, grp UNINDEXED, page UNINDEXED,
    tokenize='porter unicode61');
"""
STOP = set("""a an the of to in on at by for from with and or not is are was were be been
being it its this that these those as but if then so such than which who whom whose
should must shall may might can could would will do does did have has had""".split())
BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
AI_STATE = {"error": ""}
DEAD = set()             # models that returned 404 this session: never asked again
MAX_SOURCES = 300        # most pages shown in the sources list
AI_PAGES = 8             # pages sent to Gemini in one batch


def connect():
    con = sqlite3.connect(DB_FILE, timeout=30, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(files)")]
    if "hash" not in cols:                      # upgrade an older library
        con.execute("ALTER TABLE files ADD COLUMN hash TEXT")
    return con


# ---------- settings ----------
def load_settings():
    s = {"gemini_api_key": "", "model": "gemini-flash-latest",
         "collection": "Indian Supreme Court judgments", "general_fallback": True}
    try:
        s.update(json.load(open(SETTINGS_FILE, encoding="utf-8")))
    except Exception:
        pass
    return s

def save_settings(s):
    json.dump(s, open(SETTINGS_FILE, "w", encoding="utf-8"), indent=2)

def ai_enabled():
    return bool(load_settings().get("gemini_api_key", "").strip())


# ---------- library ----------
def stats():
    with closing(connect()) as con:
        n = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        p = con.execute("SELECT COALESCE(SUM(pages),0) FROM files").fetchone()[0]
        groups = [r[0] for r in con.execute("SELECT DISTINCT grp FROM files ORDER BY grp")]
    return n, p, groups

def items_from_folder(root):
    items = []
    for folder, _, names in os.walk(root):
        for n in sorted(names):
            if n.lower().endswith(".pdf"):
                rel = os.path.relpath(folder, root)
                grp = (os.path.basename(os.path.normpath(root)) if rel == "."
                       else rel.split(os.sep)[0])
                items.append((os.path.join(folder, n), grp))
    return items

def items_from_files(paths):
    return [(p, "Added files") for p in paths]

def _clean(t):
    t = re.sub(r"(?m)^[A-H]\s*$", "", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()

def file_hash(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def index_items(items, progress, stop):
    """Reads PDFs into the database. A file counts as done only when fully saved."""
    done, failed = 0, []
    with closing(connect()) as con:
        for path, grp in items:
            if stop.is_set():
                break
            name = os.path.basename(path)
            path = os.path.normpath(os.path.abspath(path))
            progress(done, len(items), name)
            try:
                st = os.stat(path)
                row = con.execute("SELECT size, mtime FROM files WHERE path=?", (path,)).fetchone()
                if row and row[0] == st.st_size and row[1] == st.st_mtime:
                    done += 1
                    continue
                h = file_hash(path)
                dup = con.execute("SELECT path FROM files WHERE hash=? AND path<>?",
                                  (h, path)).fetchone()
                if dup:
                    failed.append((name, "skipped, same content already in the library (%s)"
                                   % os.path.basename(dup[0])))
                    done += 1
                    continue
                doc = pymupdf.open(path)
                if doc.needs_pass:
                    raise ValueError("password protected")
                con.execute("BEGIN")
                try:
                    con.execute("DELETE FROM pages WHERE path=?", (path,))
                    con.execute("DELETE FROM files WHERE path=?", (path,))
                    for pno in range(len(doc)):
                        text = _clean(doc[pno].get_text())
                        if text:
                            con.execute("INSERT INTO pages(text, path, file, grp, page) "
                                        "VALUES (?,?,?,?,?)", (text, path, name, grp, pno + 1))
                    con.execute("INSERT INTO files(path, grp, size, mtime, pages, hash) "
                                "VALUES (?,?,?,?,?,?)",
                                (path, grp, st.st_size, st.st_mtime, len(doc), h))
                    con.execute("COMMIT")
                except Exception:
                    con.execute("ROLLBACK")
                    raise
                finally:
                    doc.close()
                done += 1
            except Exception as e:
                failed.append((name, str(e)))
    progress(done, len(items), "")
    return done, failed


# ---------- library management ----------
def list_files():
    with closing(connect()) as con:
        return con.execute("SELECT path, grp, pages FROM files ORDER BY grp, path").fetchall()

def _shrink(con):
    con.execute("INSERT INTO pages(pages) VALUES('optimize')")
    con.execute("VACUUM")

def remove_files(paths):
    with closing(connect()) as con:
        con.execute("BEGIN")
        for p in paths:
            con.execute("DELETE FROM pages WHERE path=?", (p,))
            con.execute("DELETE FROM files WHERE path=?", (p,))
        con.execute("COMMIT")
        _shrink(con)

def clear_library():
    with closing(connect()) as con:
        con.execute("BEGIN")
        con.execute("DELETE FROM pages")
        con.execute("DELETE FROM files")
        con.execute("COMMIT")
        _shrink(con)

def remove_duplicates():
    """Keeps one copy of each identical PDF. Returns how many were removed."""
    dups, seen = [], {}
    with closing(connect()) as con:
        for path, h in con.execute("SELECT path, hash FROM files ORDER BY path").fetchall():
            if not h:
                try:
                    h = file_hash(path)
                except Exception:
                    continue                        # file moved or deleted
                con.execute("UPDATE files SET hash=? WHERE path=?", (h, path))
            if h in seen:
                dups.append(path)
            else:
                seen[h] = path
    remove_files(dups)
    return len(dups)


# ---------- search ----------
def _run(con, match, limit, grp=None):
    sql = ("SELECT path, file, grp, page, snippet(pages, 0, '[', ']', ' ... ', 45) "
           "FROM pages WHERE pages MATCH ?")
    args = [match]
    if grp:
        sql += " AND grp = ?"
        args.append(grp)
    sql += " ORDER BY bm25(pages) LIMIT ?"
    args.append(limit)
    try:
        return con.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []

def plain_search(con, question, limit=100, grp=None, loose=True):
    """Keyword search on the user's own words.
    loose=False keeps only close matches (words near each other, or all words present)."""
    words = re.findall(r"[A-Za-z0-9]+", question.lower())
    q = ['"%s"' % w for w in words if w not in STOP and len(w) > 1]
    if not q:
        return []
    tiers = []
    if len(q) > 1:
        tiers.append("NEAR(%s, %d)" % (" ".join(q), max(10, 4 * len(q))))
        tiers.append(" AND ".join(q))
    else:
        tiers.append(q[0])
    if loose:
        tiers.append(" OR ".join(q))
    out, seen = [], set()
    for m in tiers:
        if len(out) >= limit:
            break
        for r in _run(con, m, limit * 2, grp):
            key = (r[0], r[3])
            if key not in seen and len(out) < limit:
                seen.add(key)
                out.append(r)
    return out

def smart_search(question, limit=MAX_SOURCES, grp=None, phrases=None):
    """Returns (phrases, results). results = list of (row, why), best first.
    If phrases is given, Gemini is not called for them."""
    raw = expand_query(question) if phrases is None else phrases
    phrases = []
    for p in raw:
        p = " ".join(re.findall(r"[A-Za-z0-9]+", p.lower()))
        if p and p not in phrases:
            phrases.append(p)
    scores, info, hits = defaultdict(float), {}, defaultdict(list)

    def add(rows, name, weight):
        for rank, r in enumerate(rows):
            key = (r[0], r[3])
            scores[key] += weight / (60 + rank)
            info.setdefault(key, r)
            if name not in hits[key]:
                hits[key].append(name)

    with closing(connect()) as con:
        for i, p in enumerate(phrases):
            add(_run(con, '"%s"' % p, 100, grp), p, max(0.4, 1.0 - 0.1 * i))
        add(plain_search(con, question, 100, grp, loose=False), "your words", 1.0)
        loose = plain_search(con, question, 100, grp, loose=True)
        add(loose, "any of your words", 0.4)
    ranked = sorted(scores, key=scores.get, reverse=True)
    # Keep the 3 best keyword pages inside the first set the AI reads, so a weak
    # AI phrase can never hide them.
    for i, r in enumerate(loose[:3]):
        key = (r[0], r[3])
        if key in ranked[:AI_PAGES]:
            continue
        if key in ranked:
            ranked.remove(key)
        ranked.insert(min(AI_PAGES - 3 + i, len(ranked)), key)
    ranked = ranked[:limit]
    return phrases, [(info[k], hits[k]) for k in ranked]

def make_sources(results):
    """All found pages for the sources list.
    'strong' = found by at least 2 different searches (used only when the AI says NONE)."""
    out = []
    for r, why in results:
        strong = len([w for w in why if w != "any of your words"]) >= 2
        out.append({"path": r[0], "file": r[1], "grp": r[2], "page": r[3],
                    "snippet": r[4], "strong": strong})
    return out

def page_text(path, page):
    with closing(connect()) as con:
        r = con.execute("SELECT text FROM pages WHERE path=? AND page=?", (path, page)).fetchone()
    return r[0] if r else ""

def pick_pages(results, skip=0, max_pages=AI_PAGES, max_chars=3000):
    """The best pages (reprints skipped) that are sent to Gemini.
    skip = how many good pages to pass over (used to read the next batch)."""
    chosen, seen = [], set()
    for r, why in results:
        text = page_text(r[0], r[3])
        sig = re.sub(r"\W+", "", text.lower())[:300]      # skip reprinted duplicates
        if not text or sig in seen:
            continue
        seen.add(sig)
        chosen.append({"path": r[0], "file": r[1], "grp": r[2], "page": r[3],
                       "text": text[:max_chars]})
        if len(chosen) >= skip + max_pages:
            break
    return chosen[skip:]


# ---------- Gemini (optional) ----------
def ask_gemini(prompt, timeout=30, models=None):
    s = load_settings()
    key = s.get("gemini_api_key", "").strip()
    if not key:
        AI_STATE["error"] = "no Gemini key (add one in Settings)"
        return None
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0}}).encode("utf-8")
    order = models or ["gemini-flash-lite-latest", s["model"], "gemini-3.5-flash"]
    for model in dict.fromkeys(order):
        if model in DEAD:
            continue
        req = urllib.request.Request(
            BASE + model + ":generateContent", data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            AI_STATE["error"] = ""
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            AI_STATE["error"] = "Google returned error %s (%s)" % (e.code, model)
            if e.code == 404:
                DEAD.add(model)
        except Exception as e:
            AI_STATE["error"] = str(e)
    return None

def cached_phrases(question):
    """Saved AI phrases for this question, or [] (never calls Gemini)."""
    s = load_settings()
    key = s["collection"] + "|" + " ".join(question.lower().split())
    try:
        return json.load(open(CACHE_FILE, encoding="utf-8")).get(key, [])
    except Exception:
        return []

def expand_query(question):
    s = load_settings()
    key = s["collection"] + "|" + " ".join(question.lower().split())
    try:
        cache = json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        cache = {}
    if key in cache:
        return cache[key]
    prompt = (
        "You help search a collection of PDF documents (" + s["collection"] + "), which "
        "are searched by exact phrases. Convert the user's question into 5 to 8 search "
        "phrases.\nRules:\n"
        "1. FIRST include the key phrases exactly as the user wrote them.\n"
        "2. Then add phrases that documents of this kind commonly use for the same concept.\n"
        "3. Each phrase must be 1 to 4 words and a real expression. Do not invent phrases.\n"
        "4. Skip generic phrases that appear in unrelated contexts.\n"
        "5. Order from most to least important.\n"
        "Return ONLY a JSON list of strings, nothing else.\n\n"
        "Example question: the accused has a right to a speedy hearing\n"
        'Example answer: ["speedy trial", "right to speedy trial", "Article 21", '
        '"delay in trial", "fair trial"]\n\nQuestion: ' + question)
    text = ask_gemini(prompt, timeout=20)
    if not text:
        return []
    m = re.search(r"\[.*\]", text, re.S)
    try:
        phrases = [str(p) for p in json.loads(m.group(0))][:8] if m else []
    except Exception:
        return []
    if phrases:
        cache[key] = phrases
        json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), indent=1)
    return phrases

def write_answer(question, pages):
    """Answers ONLY from the given pages.
    Returns (verdict, text). verdict is DIRECT, RELATED, NONE, or None if the AI failed.
    NONE is returned only when two models agree (or the only model that replied says it)."""
    s = load_settings()
    blocks = ["[%d] (%s, PDF page %d)\n%s" % (i, p["file"], p["page"], p["text"])
              for i, p in enumerate(pages, 1)]
    prompt = (
        "You answer questions using ONLY the numbered excerpts below. Never use outside "
        "knowledge. Do not add general statements, background or conclusions that the "
        "excerpts do not say in so many words.\n\n"
        "Your reply must have this exact format:\n"
        "Line 1: one label, and nothing else on that line:\n"
        "  DIRECT   (the excerpts directly answer the question)\n"
        "  RELATED  (the excerpts discuss the topic but do not directly state what was asked, "
        "for example when the question is a general statement)\n"
        "  NONE     (the excerpts are unrelated to the question)\n"
        "Line 2 onwards: for DIRECT or RELATED, write 3 to 6 plain sentences using only the "
        "excerpts. After every claim, cite the excerpt number like [1] or [2][4]. For NONE, "
        "write nothing more.\n\n"
        "QUESTION: " + question + "\n\nEXCERPTS:\n\n" + "\n\n".join(blocks))
    none_votes = 0
    for model in dict.fromkeys([s["model"], "gemini-3.5-flash", "gemini-flash-lite-latest"]):
        text = ask_gemini(prompt, timeout=30, models=[model])
        if not text:
            continue
        parts = text.strip().split("\n", 1)
        label = re.sub(r"[^A-Za-z]", "", parts[0]).upper()
        body = parts[1].strip() if len(parts) > 1 else ""
        if label == "NONE":
            none_votes += 1
            if none_votes >= 2:                # two models agree: stop asking
                return "NONE", ""
            continue
        if label == "RELATED" and body:
            return "RELATED", body
        if label == "DIRECT" and body:
            return "DIRECT", body
        AI_STATE["error"] = "the AI reply was not in the expected format"
    if none_votes:
        return "NONE", ""
    return None, ""

def general_answer(question):
    """Used ONLY when the documents do not cover the topic. Gemini answers from general
    knowledge. The app always labels this clearly. Returns text or None."""
    prompt = (
        "Answer the question below from your general knowledge, in 4 to 8 plain sentences. "
        "Be accurate and neutral. If the question is about law, give general information only, "
        "not legal advice. Do NOT quote or invent case names, citations, section numbers or "
        "page numbers unless you are certain they are correct. If you are not sure about "
        "something, say so.\n\nQUESTION: " + question)
    text = ask_gemini(prompt, timeout=25)
    return text.strip() if text else None