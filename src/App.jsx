import { useEffect, useMemo, useState } from "react";

const LETTERS = ["A", "B", "C", "D"];

function getCorrectLetter(item) {
  const direct = item.correct_answer;
  if (typeof direct === "string" && LETTERS.includes(direct)) return direct;

  const orange = item.expected_orange;
  if (typeof orange === "string" && LETTERS.includes(orange)) return orange;
  if (Array.isArray(orange) && LETTERS.includes(orange[0])) return orange[0];

  const green = item.selected_green;
  if (typeof green === "string" && LETTERS.includes(green)) return green;
  if (Array.isArray(green) && LETTERS.includes(green[0])) return green[0];

  return null;
}

export default function App() {
  const [items, setItems] = useState([]);
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState(null);
  const [score, setScore] = useState({ ok: 0, bad: 0 });

  useEffect(() => {
    fetch("./questions_with_marks.json")
      .then((r) => r.json())
      .then((data) => {
        const shuffled = [...data];
        for (let i = shuffled.length - 1; i > 0; i -= 1) {
          const j = Math.floor(Math.random() * (i + 1));
          [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        setItems(shuffled);
      })
      .catch(() => setItems([]));
  }, []);

  const current = items[idx];
  const correct = useMemo(() => (current ? getCorrectLetter(current) : null), [current]);

  const totalDone = score.ok + score.bad;
  const accuracy = totalDone ? Math.round((score.ok / totalDone) * 100) : 0;

  function onPick(letter) {
    if (!current || picked) return;
    setPicked(letter);
    if (!correct) return;
    setScore((s) => (letter === correct ? { ...s, ok: s.ok + 1 } : { ...s, bad: s.bad + 1 }));
  }

  function nextQuestion() {
    setPicked(null);
    setIdx((i) => (i + 1) % items.length);
  }

  function prevQuestion() {
    setPicked(null);
    setIdx((i) => (i - 1 + items.length) % items.length);
  }

  if (!items.length) {
    return <main className="wrap"><p className="loading">Cargando preguntas...</p></main>;
  }

  return (
    <main className="wrap">
      <header className="top">
        <div>
          <strong>{current.exam}</strong>
          <p>Pregunta {idx + 1} de {items.length}</p>
        </div>
        <div className="stats">
          <span>✅ {score.ok}</span>
          <span>❌ {score.bad}</span>
          <span>{accuracy}%</span>
        </div>
      </header>

      <section className="card">
        <h1>{current.question}</h1>
        <div className="answers">
          {LETTERS.map((letter) => {
            const text = current.options?.[letter] || "";
            const isPicked = picked === letter;
            const isCorrect = picked && correct === letter;
            const isWrongPicked = picked && isPicked && correct !== letter;

            let cls = "answer";
            if (isCorrect) cls += " ok";
            if (isWrongPicked) cls += " bad";
            if (isPicked) cls += " picked";

            return (
              <button key={letter} className={cls} onClick={() => onPick(letter)} disabled={Boolean(picked)}>
                <span className="letter">{letter}</span>
                <span>{text}</span>
              </button>
            );
          })}
        </div>

        {picked && (
          <div className="feedback">
            {!correct ? (
              <p className="badText">No hay respuesta correcta definida para esta pregunta.</p>
            ) : picked === correct ? (
              <p className="good">Correcta</p>
            ) : (
              <p className="badText">Incorrecta. La correcta es: <strong>{correct}</strong></p>
            )}
          </div>
        )}
      </section>

      <footer className="nav">
        <button onClick={prevQuestion}>Anterior</button>
        <button onClick={nextQuestion}>Siguiente</button>
      </footer>
    </main>
  );
}
