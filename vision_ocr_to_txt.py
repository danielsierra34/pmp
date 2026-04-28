from pathlib import Path
import base64
import json
import time
from urllib import request, error


BASE_DIR = Path(".")
INPUT_DIRS = [BASE_DIR / "pmp_1_pages", BASE_DIR / "pmp_2_pages"]
OUTPUT_SUFFIX = "_txt"
VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
BATCH_SIZE = 8


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def chunked(items, n):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def annotate_batch(api_key: str, image_paths: list[Path]) -> list[dict]:
    reqs = []
    for p in image_paths:
        img_b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        reqs.append(
            {
                "image": {"content": img_b64},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                "imageContext": {"languageHints": ["en", "es"]},
            }
        )

    payload = json.dumps({"requests": reqs}).encode("utf-8")
    url = f"{VISION_URL}?key={api_key}"
    req = request.Request(
        url=url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    for attempt in range(4):
        try:
            with request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("responses", [])
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if attempt == 3:
                raise RuntimeError(f"Vision API HTTP {e.code}: {body[:700]}") from e
            time.sleep(2**attempt)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)

    return []


def extract_text(item: dict) -> str:
    if "error" in item:
        err = item["error"]
        return f"[VISION_ERROR] code={err.get('code')} message={err.get('message', '')}\n"
    if "fullTextAnnotation" in item:
        return item["fullTextAnnotation"].get("text", "") or ""
    ta = item.get("textAnnotations") or []
    if ta:
        return ta[0].get("description", "") or ""
    return ""


def main() -> None:
    env = load_env(BASE_DIR / ".env")
    api_key = env.get("GOOGLE_API_KEY", "").strip()
    if not api_key or "PASTE_YOUR" in api_key:
        raise SystemExit("Set GOOGLE_API_KEY in .env and retry.")

    total_written = 0
    for in_dir in INPUT_DIRS:
        if not in_dir.exists():
            print(f"[WARN] Missing input directory: {in_dir}")
            continue

        images = sorted(in_dir.glob("*.png"))
        out_dir = BASE_DIR / f"{in_dir.name}{OUTPUT_SUFFIX}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Processing {in_dir.name}: {len(images)} images -> {out_dir.name}")

        done = 0
        for batch in chunked(images, BATCH_SIZE):
            responses = annotate_batch(api_key, batch)

            for img_path, item in zip(batch, responses):
                text = extract_text(item)
                out_path = out_dir / f"{img_path.stem}.txt"
                out_path.write_text(text, encoding="utf-8")
                done += 1
                total_written += 1

            if done % 10 == 0 or done == len(images):
                print(f"  - {in_dir.name}: {done}/{len(images)}")

    print(f"Done. TXT files written: {total_written}")


if __name__ == "__main__":
    main()
