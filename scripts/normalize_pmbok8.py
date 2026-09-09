import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/home/debian/a/Examenes unificados.json")
DATASET = ROOT / "data" / "pmbok-8"
PROCESSED = DATASET / "processed" / "questions_with_marks.json"
PUBLIC = ROOT / "public" / "data" / "pmbok-8" / "questions_with_marks.json"
ORIGINAL = DATASET / "source" / "Examenes unificados.json"


def normalize_dimension(value: str) -> str:
    dimension = " ".join((value or "").split())
    return {"Business  Environment": "Business Environment", "No especificado": "Unspecified"}.get(
        dimension, dimension or "Unspecified"
    )


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Source file not found: {SOURCE}")

    source_data = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    questions = source_data.get("preguntas", [])
    converted = []

    for question in questions:
        options = {option["id"].upper(): option.get("texto", "").strip() for option in question.get("opciones", [])}
        if len(options) < 2 or not set(options).issubset({"A", "B", "C", "D"}):
            raise ValueError(f"Question {question.get('numero')} has an invalid option set: {sorted(options)}")

        correct = str(question.get("respuesta_correcta", "")).strip().upper()
        if correct not in options:
            raise ValueError(f"Question {question.get('numero')} has invalid correct answer: {correct}")

        converted.append(
            {
                "row": question.get("numero"),
                "exam": "PMBOK 8",
                "question": question.get("texto", "").strip(),
                "options": options,
                "correct_answer": correct,
                "dimension": normalize_dimension(question.get("tema", "")),
            }
        )

    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    ORIGINAL.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED.write_text(json.dumps(converted, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(PROCESSED, PUBLIC)
    shutil.copy2(SOURCE, ORIGINAL)
    print(f"Converted {len(converted)} questions")
    print(f"Processed: {PROCESSED}")
    print(f"Public: {PUBLIC}")


if __name__ == "__main__":
    main()
