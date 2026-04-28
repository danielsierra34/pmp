import re
import json
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import fitz
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

PDF_FILES = ["pmp_1.pdf", "pmp_2.pdf"]
CREDENTIALS_FILE = "oceanic-craft-446616-c3-9cb2a8b2d2a5.json"
SHEET_ID = "1GiIGc4ZmQpJBu8_qNfrFdAJTkOYR3i7JcvgJcHhH2v4"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass
class QuestionRecord:
    question: str
    options: Dict[str, str]
    option_marked: Dict[str, bool] = field(default_factory=dict)
    explanation: str = ""
    correct: str = ""
    source: str = ""


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_line(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("•", " ")
    text = text.replace("→", " ")
    text = re.sub(r"\b\d+\s*/\s*\d+\s*point\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_noise(line: str) -> bool:
    l = line.lower().strip()
    if not l:
        return True
    patterns = [
        r"^set\d+",
        r"^back$",
        r"^practice assignment",
        r"^your grade",
        r"^your latest",
        r"^next item",
        r"^\d+/\d+ ?point",
    ]
    return any(re.search(p, l) for p in patterns)


def ocr_page(engine: RapidOCR, page: fitz.Page) -> List[str]:
    img = None
    pdict = page.get_text("dict")
    img_blocks = [b for b in pdict.get("blocks", []) if b.get("type") == 1 and b.get("image")]
    if img_blocks:
        arr = np.frombuffer(img_blocks[0]["image"], dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    result, _ = engine(img)
    if not result:
        return []

    rows: List[Tuple[float, float, str]] = []
    for box, text, conf in result:
        y = min(pt[1] for pt in box)
        x = min(pt[0] for pt in box)
        t = clean_line(text)
        if t:
            rows.append((y, x, t))

    rows.sort(key=lambda r: (r[0], r[1]))

    merged: List[str] = []
    current_y = None
    current_parts: List[str] = []

    for y, x, t in rows:
        if current_y is None or abs(y - current_y) <= 10:
            current_parts.append(t)
            current_y = y if current_y is None else (current_y + y) / 2
        else:
            line = normalize_spaces(" ".join(current_parts))
            if line:
                merged.append(line)
            current_parts = [t]
            current_y = y

    if current_parts:
        line = normalize_spaces(" ".join(current_parts))
        if line:
            merged.append(line)

    return merged


def parse_question_blocks(lines: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    start_re = re.compile(r"^\d+\.\s*")
    opt_re = re.compile(r"^(?:[O0Q]?\s*)?[A-D][\.)]\s*|^[O0Q]\s*[A-D]\s+", re.IGNORECASE)

    starts: List[int] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if start_re.match(line):
            starts.append(i)
            continue
        if line.endswith("?"):
            lookahead = lines[i + 1 : i + 10]
            opt_count = sum(1 for x in lookahead if opt_re.match(x.strip()))
            if opt_count >= 2:
                starts.append(i)

    starts = sorted(set(starts))
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block = [x.strip() for x in lines[s:e] if x.strip()]
        if block:
            blocks.append(block)

    return blocks


def parse_options_and_text(block: List[str]) -> QuestionRecord | None:
    option_start = re.compile(r"^([O0Q]?\s*)([A-D])[\.)]\s*(.*)$", re.IGNORECASE)
    option_start_marker = re.compile(r"^([O0Q]\s*)([A-D])\s+(.*)$", re.IGNORECASE)
    option_only = re.compile(r"^([O0Q]?\s*)([A-D])(?:[\.)])?\s*$", re.IGNORECASE)
    score_line = re.compile(r"^\d+\/\d+\s*point", re.IGNORECASE)

    qline = block[0]
    qtext = re.sub(r"^\d+\.\s*", "", qline).strip()
    pre_option_lines: List[str] = []
    options: Dict[str, str] = {}
    option_marked: Dict[str, bool] = {"A": False, "B": False, "C": False, "D": False}
    current_opt = None
    explanation_lines: List[str] = []
    in_expl = False

    for line in block[1:]:
        l = line.strip()
        if is_noise(l) or score_line.search(l):
            continue
        if re.search(r"\bcorrect\b", l, flags=re.IGNORECASE):
            in_expl = True
            continue

        if in_expl:
            if not is_noise(l):
                explanation_lines.append(l)
            continue

        m = option_start.match(l) or option_start_marker.match(l)
        if m:
            marker = m.group(1).strip().upper()
            letter = m.group(2).upper()
            text = m.group(3).strip()
            options[letter] = text
            if marker in {"O", "0", "Q"}:
                option_marked[letter] = True
            current_opt = letter
            continue

        m2 = option_only.match(l)
        if m2:
            marker = m2.group(1).strip().upper()
            letter = m2.group(2).upper()
            options[letter] = options.get(letter, "")
            if marker in {"O", "0", "Q"}:
                option_marked[letter] = True
            current_opt = letter
            continue

        if current_opt and len(options) > 0 and len(options) <= 4 and not re.match(r"^\d+\.\s*", l):
            # continuation of option text
            options[current_opt] = normalize_spaces((options.get(current_opt, "") + " " + l).strip())
        else:
            pre_option_lines.append(l)

    question_full = normalize_spaces(" ".join([qtext] + pre_option_lines))

    # If A is missing but B-D exist, OCR often dropped the "A." prefix.
    if "A" not in options and all(k in options for k in ["B", "C", "D"]) and pre_option_lines:
        guessed_a = pre_option_lines.pop(-1)
        if guessed_a and not guessed_a.endswith("?"):
            options["A"] = guessed_a
            question_full = normalize_spaces(" ".join([qtext] + pre_option_lines))

    # Keep only A-D
    options = {k: normalize_spaces(v) for k, v in options.items() if k in {"A", "B", "C", "D"} and v}

    if len(options) < 4 or not question_full:
        return None

    explanation = normalize_spaces(" ".join(explanation_lines))
    return QuestionRecord(question=question_full, options=options, option_marked=option_marked, explanation=explanation)


def tokenize(s: str) -> set:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if len(t) >= 4]
    return set(toks)


def guess_correct_option(options: Dict[str, str], explanation: str, option_marked: Dict[str, bool]) -> str:
    exp_toks = tokenize(explanation)
    best = "A"
    best_score = -1.0
    marked_letters = [k for k, v in option_marked.items() if v]
    has_explanation = len(explanation.strip()) >= 25

    for letter in ["A", "B", "C", "D"]:
        opt = options.get(letter, "")
        otoks = tokenize(opt)
        overlap = len(exp_toks & otoks)
        if not exp_toks or not otoks:
            jacc = 0.0
        else:
            jacc = overlap / max(1, len(exp_toks | otoks))
        mark_bonus = 0.0
        if not has_explanation:
            if len(marked_letters) == 1 and letter == marked_letters[0]:
                mark_bonus = 4.0
            elif option_marked.get(letter, False):
                mark_bonus = 1.0
        else:
            if option_marked.get(letter, False):
                mark_bonus = 0.25
        score = overlap * 10 + jacc * 5 + mark_bonus + (len(opt) / 1000.0)
        if score > best_score:
            best_score = score
            best = letter

    return best


def dedupe_records(records: List[QuestionRecord]) -> List[QuestionRecord]:
    def canon_q(s: str) -> str:
        s = s.lower()
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    out: List[QuestionRecord] = []
    seen_q: List[str] = []

    for r in records:
        cq = canon_q(r.question)
        if len(cq) < 30:
            continue

        dup_idx = None
        for i, sq in enumerate(seen_q):
            ratio = difflib.SequenceMatcher(a=cq, b=sq).ratio()
            if ratio >= 0.90:
                dup_idx = i
                break

        if dup_idx is None:
            out.append(r)
            seen_q.append(cq)
        else:
            existing = out[dup_idx]
            if len(r.question) > len(existing.question):
                existing.question = r.question
            for k in ["A", "B", "C", "D"]:
                if len(r.options.get(k, "")) > len(existing.options.get(k, "")):
                    existing.options[k] = r.options[k]
            if len(r.explanation) > len(existing.explanation):
                existing.explanation = r.explanation

    out.sort(key=lambda x: x.question.lower())
    return out


def write_to_sheet(records: List[QuestionRecord]) -> None:
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)

    values = [["Pregunta", "Respuesta A", "Respuesta B", "Respuesta C", "Respuesta D"]]
    for r in records:
        values.append([
            r.question,
            r.options.get("A", ""),
            r.options.get("B", ""),
            r.options.get("C", ""),
            r.options.get("D", ""),
        ])

    service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range="A:E"
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range="A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

    # Get first sheet ID
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheet_id = meta["sheets"][0]["properties"]["sheetId"]

    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 5,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat.textFormat.bold"
            }
        }
    ]

    green = {"red": 0.85, "green": 0.95, "blue": 0.85}

    for idx, r in enumerate(records, start=1):
        col = {"A": 1, "B": 2, "C": 3, "D": 4}.get(r.correct, 1)
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": idx,
                        "endRowIndex": idx + 1,
                        "startColumnIndex": col,
                        "endColumnIndex": col + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": green
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
        )

    service.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": requests}
    ).execute()


def main() -> None:
    engine = RapidOCR()
    all_records: List[QuestionRecord] = []

    for pdf in PDF_FILES:
        doc = fitz.open(pdf)
        print(f"Processing {pdf} with {doc.page_count} pages...")
        for i in range(doc.page_count):
            lines = ocr_page(engine, doc.load_page(i))
            blocks = parse_question_blocks(lines)
            for b in blocks:
                rec = parse_options_and_text(b)
                if rec:
                    rec.source = f"{pdf}:page_{i+1}"
                    all_records.append(rec)
            if (i + 1) % 5 == 0:
                print(f"  - {pdf}: page {i+1}/{doc.page_count}")

    deduped = dedupe_records(all_records)

    for r in deduped:
        r.correct = guess_correct_option(r.options, r.explanation, r.option_marked)

    print(f"Extracted candidate records: {len(all_records)}")
    print(f"Deduped records: {len(deduped)}")

    # Local audit file
    audit = []
    for r in deduped:
        audit.append(
            {
                "question": r.question,
                "A": r.options.get("A", ""),
                "B": r.options.get("B", ""),
                "C": r.options.get("C", ""),
                "D": r.options.get("D", ""),
                "correct": r.correct,
                "explanation": r.explanation,
                "source": r.source,
            }
        )

    Path("extracted_questions.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    write_to_sheet(deduped)
    print("Sheet updated successfully.")


if __name__ == "__main__":
    main()
