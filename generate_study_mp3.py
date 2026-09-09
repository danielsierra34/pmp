import argparse
import asyncio
import json
import re
from pathlib import Path

import edge_tts


def get_correct_letter(item: dict) -> str | None:
    direct = item.get("correct_answer")
    if isinstance(direct, str) and direct in {"A", "B", "C", "D"}:
        return direct
    if isinstance(direct, list) and direct and direct[0] in {"A", "B", "C", "D"}:
        return direct[0]

    orange = item.get("expected_orange")
    if isinstance(orange, str) and orange in {"A", "B", "C", "D"}:
        return orange
    if isinstance(orange, list) and orange and orange[0] in {"A", "B", "C", "D"}:
        return orange[0]

    green = item.get("selected_green")
    if isinstance(green, str) and green in {"A", "B", "C", "D"}:
        return green
    if isinstance(green, list) and green and green[0] in {"A", "B", "C", "D"}:
        return green[0]
    return None


def clean_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def to_study_script(items: list[dict], exam_filter: str | None, mode: str) -> str:
    lines: list[str] = []
    current_exam = None
    spoken_idx = 0

    for item in items:
        exam = clean_text(item.get("exam", ""))
        if exam_filter and exam_filter != exam:
            continue

        if exam != current_exam:
            current_exam = exam
            lines.append(f"{exam}.")

        q = clean_text(item.get("question") or item.get("question_es") or "")
        options = item.get("options") or item.get("options_es") or {}
        a = clean_text(options.get("A", ""))
        b = clean_text(options.get("B", ""))
        c = clean_text(options.get("C", ""))
        d = clean_text(options.get("D", ""))
        correct = get_correct_letter(item)

        if not q:
            continue

        spoken_idx += 1

        if mode == "correct-only":
            lines.append(f"Question {spoken_idx}. {q}")
            if correct and options.get(correct):
                corr_text = clean_text(options.get(correct, ""))
                lines.append(f"Correct answer: {correct}. {corr_text}")
            elif correct:
                lines.append(f"Correct answer: {correct}.")
            else:
                lines.append("Correct answer not available.")
            lines.append("Next question.")
        else:
            lines.append(f"Question {spoken_idx}. {q}")
            lines.append(f"Option A. {a}")
            lines.append(f"Option B. {b}")
            lines.append(f"Option C. {c}")
            lines.append(f"Option D. {d}")
            if correct:
                lines.append(f"Correct answer. {correct}.")
            lines.append("Next question.")

    return "\n".join(lines)


def split_chunks(text: str, max_chars: int = 2500) -> list[str]:
    parts = re.split(r"(?<=[\.\?\!])\s+", text)
    chunks: list[str] = []
    cur = ""

    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(cur) + len(p) + 1 <= max_chars:
            cur = f"{cur} {p}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


async def synthesize_chunks(chunks: list[str], voice: str, rate: str, pitch: str, tmp_dir: Path) -> list[Path]:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_files: list[Path] = []

    for i, chunk in enumerate(chunks, start=1):
        out = tmp_dir / f"chunk_{i:03d}.mp3"
        communicate = edge_tts.Communicate(text=chunk, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(str(out))
        out_files.append(out)
        print(f"Chunk {i}/{len(chunks)} ready")
    return out_files


def concat_mp3(parts: list[Path], output_file: Path) -> None:
    with output_file.open("wb") as w:
        for p in parts:
            w.write(p.read_bytes())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate study MP3 from questions JSON")
    parser.add_argument("--input", default="data/pmbok-7/processed/questions_with_marks.json", help="Input JSON path")
    parser.add_argument("--output", default="data/pmbok-7/audio/full/pmp_study_en_correct_only.mp3", help="Output MP3 file")
    parser.add_argument("--voice", default="en-US-AriaNeural", help="Edge TTS voice")
    parser.add_argument("--rate", default="+0%", help="Rate, e.g. +10%")
    parser.add_argument("--pitch", default="+0Hz", help="Pitch, e.g. +0Hz")
    parser.add_argument("--exam", default=None, help="Exact exam filter, e.g. 'Examen 1'")
    parser.add_argument("--mode", choices=["full", "correct-only"], default="correct-only", help="Narration mode")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Not found: {input_path}")

    items = json.loads(input_path.read_text(encoding="utf-8"))
    script = to_study_script(items, args.exam, args.mode)
    script_file = Path(args.output).parent / "study_script_en.txt"
    script_file.write_text(script, encoding="utf-8")
    print(f"Study script saved to {script_file}")

    chunks = split_chunks(script, max_chars=2500)
    if not chunks:
        raise SystemExit("No content to synthesize.")

    tmp_dir = Path(".tts_tmp")
    parts = await synthesize_chunks(chunks, args.voice, args.rate, args.pitch, tmp_dir)
    output_path = Path(args.output)
    concat_mp3(parts, output_path)
    print(f"MP3 generated: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
