import argparse
import asyncio
import json
import re
from pathlib import Path

import edge_tts


def get_correct_letter(item: dict) -> str | None:
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


def to_study_script(items: list[dict], exam_filter: str | None) -> str:
    lines: list[str] = []
    current_exam = None

    for i, item in enumerate(items, start=1):
        exam = clean_text(item.get("exam", ""))
        if exam_filter and exam_filter != exam:
            continue

        if exam != current_exam:
            current_exam = exam
            lines.append(f"{exam}.")

        q = clean_text(item.get("question_es") or item.get("question") or "")
        options = item.get("options_es") or item.get("options") or {}
        a = clean_text(options.get("A", ""))
        b = clean_text(options.get("B", ""))
        c = clean_text(options.get("C", ""))
        d = clean_text(options.get("D", ""))
        correct = get_correct_letter(item)

        if not q:
            continue

        lines.append(f"Pregunta {i}. {q}")
        lines.append(f"Opción A. {a}")
        lines.append(f"Opción B. {b}")
        lines.append(f"Opción C. {c}")
        lines.append(f"Opción D. {d}")
        if correct:
            lines.append(f"Respuesta correcta. {correct}.")
        lines.append("Siguiente pregunta.")

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
        print(f"Chunk {i}/{len(chunks)} listo")
    return out_files


def concat_mp3(parts: list[Path], output_file: Path) -> None:
    with output_file.open("wb") as w:
        for p in parts:
            w.write(p.read_bytes())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Genera audio MP3 de estudio desde questions_with_marks_es.json")
    parser.add_argument("--input", default="questions_with_marks_es.json", help="Ruta del JSON de entrada")
    parser.add_argument("--output", default="pmp_study_es.mp3", help="Nombre del MP3 de salida")
    parser.add_argument("--voice", default="es-CO-SalomeNeural", help="Voz Edge TTS")
    parser.add_argument("--rate", default="+0%", help="Velocidad, ej: +10%")
    parser.add_argument("--pitch", default="+0Hz", help="Tono, ej: +0Hz")
    parser.add_argument("--exam", default=None, help="Filtra por examen exacto, ej: 'Examen 1'")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"No existe: {input_path}")

    items = json.loads(input_path.read_text(encoding="utf-8"))
    script = to_study_script(items, args.exam)
    script_file = Path("study_script_es.txt")
    script_file.write_text(script, encoding="utf-8")
    print(f"Script de estudio guardado en {script_file}")

    chunks = split_chunks(script, max_chars=2500)
    if not chunks:
        raise SystemExit("No hay contenido para sintetizar.")

    tmp_dir = Path(".tts_tmp")
    parts = await synthesize_chunks(chunks, args.voice, args.rate, args.pitch, tmp_dir)
    output_path = Path(args.output)
    concat_mp3(parts, output_path)
    print(f"MP3 generado: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
