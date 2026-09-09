# PMP question datasets

Each PMBOK version has its own directory so source material, processed data,
and generated audio do not get mixed between versions.

## Layout

```text
data/
  pmbok-7/
    source/
      pdfs/
      pages/exam-1/
      pages/exam-2/
      ocr/exam-1/
      ocr/exam-2/
    processed/
    audio/
  pmbok-8/
    source/
    processed/
    audio/
```

Place PMBOK 8 PDFs in `data/pmbok-8/source/pdfs/`. Generated page images,
OCR text, JSON, and audio should stay inside the corresponding PMBOK 8
directory.

The app currently loads the PMBOK 8 dataset from
`public/data/pmbok-8/questions_with_marks.json`. The PMBOK 7 dataset remains
available under `public/data/pmbok-7/`.
