import argparse
import asyncio
import json
from pathlib import Path

import edge_tts
import av


def clean_text(s: str) -> str:
    return " ".join((s or "").split())


def get_correct_text(item: dict) -> str:
    correct = item.get("correct_answer")
    options = item.get("options") or {}
    if isinstance(correct, str) and correct in {"A", "B", "C", "D"}:
        return clean_text(options.get(correct, ""))
    return ""


def build_prompt(item: dict, number: int) -> str:
    question = clean_text(item.get("question") or "")
    correct_text = get_correct_text(item)

    if correct_text:
        return f"Question {number}. {question}. Correct answer. {correct_text}."
    return f"Question {number}. {question}. Correct answer not available."


def transcode_mp3(source_path: Path, out_path: Path, bitrate: int) -> None:
    with av.open(str(source_path)) as source:
        input_stream = source.streams.audio[0]
        with av.open(str(out_path), mode="w", format="mp3") as target:
            output_stream = target.add_stream("libmp3lame", rate=input_stream.rate or 24000)
            output_stream.bit_rate = bitrate * 1000
            output_stream.layout = "mono"
            for frame in source.decode(audio=0):
                for packet in output_stream.encode(frame):
                    target.mux(packet)
            for packet in output_stream.encode():
                target.mux(packet)


async def synthesize(text: str, out_path: Path, voice: str, rate: str, pitch: str, bitrate: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = out_path.with_suffix(".source.mp3")
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    try:
        await comm.save(str(source_path))
        transcode_mp3(source_path, out_path, bitrate)
    finally:
        source_path.unlink(missing_ok=True)


async def generate_one(index: int, item: dict, outdir: Path, voice: str, rate: str, pitch: str, bitrate: int, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        prompt = build_prompt(item, index)
        filename = f"Q{index:03d}.mp3"
        out_path = outdir / filename
        if not out_path.exists() or out_path.stat().st_size == 0:
            last_error = None
            for attempt in range(3):
                try:
                    await synthesize(prompt, out_path, voice, rate, pitch, bitrate)
                    last_error = None
                    break
                except Exception as error:
                    last_error = error
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
            if last_error is not None:
                raise last_error
        print(f"[{index}] {filename}")
        return {
            "row": item.get("row"),
            "file": filename,
            "exam": item.get("exam"),
            "question": item.get("question"),
            "correct_answer": item.get("correct_answer"),
            "bitrate_kbps": bitrate,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one MP3 per question from the PMP JSON.")
    parser.add_argument("--input", default="data/pmbok-7/processed/questions_with_marks.json", help="Input JSON file")
    parser.add_argument("--outdir", default="data/pmbok-8/audio/per-question-96kbps", help="Output folder for per-question MP3s")
    parser.add_argument("--voice", default="en-US-AriaNeural", help="Edge TTS voice")
    parser.add_argument("--rate", default="+0%", help="Speech rate")
    parser.add_argument("--pitch", default="+0Hz", help="Speech pitch")
    parser.add_argument("--bitrate", type=int, default=96, choices=[32, 48, 64, 80, 96, 128], help="MP3 bitrate in kbps")
    parser.add_argument("--concurrency", type=int, default=8, help="Number of questions processed in parallel")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of questions to generate")
    args = parser.parse_args()

    items = json.loads(Path(args.input).read_text(encoding="utf-8"))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    total = len(items) if args.limit <= 0 else min(len(items), args.limit)
    manifest = []

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    tasks = [
        generate_one(idx, item, outdir, args.voice, args.rate, args.pitch, args.bitrate, semaphore)
        for idx, item in enumerate(items[:total], start=1)
    ]
    manifest = await asyncio.gather(*tasks)

    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. Wrote {total} MP3 files to {outdir}")


if __name__ == "__main__":
    asyncio.run(main())
