import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

const LETTERS = ["A", "B", "C", "D"];
const CHART_MODES = [
  { id: "percent", label: "%" },
  { id: "presented", label: "Contestadas" },
  { id: "available", label: "Disponibles" },
];

function DimensionIcon({ dimension }) {
  if (dimension === "People") {
    return <svg viewBox="0 0 24 24" className="dimension-icon" aria-hidden="true"><circle cx="9" cy="8" r="3" /><path d="M3.5 19c.4-3 2.2-5 5.5-5s5.1 2 5.5 5" /><path d="M15 5.5a3 3 0 0 1 0 5.8M17 14c2.1.5 3.4 2.1 3.5 5" /></svg>;
  }
  if (dimension === "Process") {
    return <svg viewBox="0 0 24 24" className="dimension-icon" aria-hidden="true"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></svg>;
  }
  if (dimension === "Business Environment") {
    return <svg viewBox="0 0 24 24" className="dimension-icon" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5h8v2M3 12h18M10 12v2h4v-2" /></svg>;
  }
  return <svg viewBox="0 0 24 24" className="dimension-icon" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 3.5v8.5h8.5M12 12l6 6" /></svg>;
}

function DimensionChart({ stats, mode, totalPresented, totalAvailable }) {
  const chartRef = useRef(null);

  useEffect(() => {
    const chart = echarts.init(chartRef.current);
    const dimensions = Object.keys(stats).sort();
    const axisMax = mode === "percent"
      ? 100
      : mode === "presented"
        ? Math.max(totalPresented, 1)
        : Math.max(totalAvailable, 1);
    const valueFor = (item, correct) => {
      if (mode === "percent") {
        return item.attempts ? Math.round(((correct ? item.correct : item.attempts - item.correct) / item.attempts) * 100) : 0;
      }
      return correct ? item.correct : item.attempts - item.correct;
    };
    chart.setOption({
      animationDuration: 450,
      grid: { left: 125, right: 24, top: 12, bottom: 36 },
      xAxis: {
        type: "value",
        min: 0,
        max: axisMax,
        axisLabel: { formatter: (value) => mode === "percent" ? `${value}%` : value },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: dimensions,
        axisLabel: { color: "#334155" },
      },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value) => `${value}%`,
      },
      legend: { bottom: 0, data: ["Aciertos", "Desaciertos"] },
      series: [
        {
          name: "Aciertos",
          type: "bar",
          stack: "total",
          data: dimensions.map((dimension) => valueFor(stats[dimension], true)),
          barMaxWidth: 24,
          itemStyle: { color: "#0f766e" },
        },
        {
          name: "Desaciertos",
          type: "bar",
          stack: "total",
          data: dimensions.map((dimension) => valueFor(stats[dimension], false)),
          barMaxWidth: 24,
          itemStyle: { color: "#e11d48" },
        },
      ],
    });

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [stats]);

  return <div className="dimension-chart" ref={chartRef} aria-label="Desempeño por dimensión" />;
}

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
  const [dimensionStats, setDimensionStats] = useState({});
  const [showProgress, setShowProgress] = useState(false);
  const [chartMode, setChartMode] = useState("percent");

  useEffect(() => {
    fetch("./data/pmbok-8/questions_with_marks.json")
      .then((r) => r.json())
      .then((data) => {
        const initialStats = {};
        data.forEach((item) => {
          const dimension = item.dimension || item.tema || "Unspecified";
          initialStats[dimension] = { attempts: 0, correct: 0 };
        });
        setDimensionStats(initialStats);
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
  const dimensions = Object.keys(dimensionStats).sort();
  const chartStats = Object.fromEntries(
    Object.entries(dimensionStats).filter(([dimension]) => dimension !== "Unspecified")
  );
  chartStats.Total = { attempts: totalDone, correct: score.ok };

  function onPick(letter) {
    if (!current || picked) return;
    setPicked(letter);
    if (!correct) return;
    const isCorrect = letter === correct;
    setScore((s) => (isCorrect ? { ...s, ok: s.ok + 1 } : { ...s, bad: s.bad + 1 }));
    const dimension = current.dimension || current.tema || "Unspecified";
    setDimensionStats((stats) => ({
      ...stats,
      [dimension]: {
        attempts: (stats[dimension]?.attempts || 0) + 1,
        correct: (stats[dimension]?.correct || 0) + (isCorrect ? 1 : 0),
      },
    }));
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
        <div className="dimension-stats" aria-label="Resultados por dimensión">
          {dimensions.map((dimension) => {
            const result = dimensionStats[dimension];
            const isTotal = dimension === "Unspecified";
            const attempts = isTotal ? totalDone : result.attempts;
            const correctAnswers = isTotal ? score.ok : result.correct;
            const dimensionAccuracy = attempts
              ? Math.round((correctAnswers / attempts) * 100)
              : 0;
            return (
              <div className="dimension-stat" key={dimension}>
                <strong title={isTotal ? "Total" : dimension} aria-label={isTotal ? "Total" : dimension}>
                  <DimensionIcon dimension={isTotal ? "Total" : dimension} />
                </strong>
                <span>✅ {correctAnswers}</span>
                <span>❌ {attempts - correctAnswers}</span>
                <span>{dimensionAccuracy}%</span>
              </div>
            );
          })}
        </div>
      </header>

      <section className="card">
        <h1>{current.question}</h1>
        <p className="question-dimension">Dimensión: <strong>{current.dimension || current.tema || "Unspecified"}</strong></p>
        <div className="answers">
          {LETTERS.filter((letter) => current.options?.[letter]).map((letter) => {
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
        <button onClick={() => setShowProgress(true)}>Progreso</button>
        <button onClick={nextQuestion}>Siguiente</button>
      </footer>

      {showProgress && (
        <div className="modal-backdrop" onClick={() => setShowProgress(false)}>
          <section className="progress-modal" role="dialog" aria-modal="true" aria-labelledby="progress-title" onClick={(event) => event.stopPropagation()}>
            <div className="modal-heading">
              <div>
                <p className="eyebrow">Resultado acumulado</p>
                <h2 id="progress-title">Progreso por dimensión</h2>
              </div>
              <button className="close-modal" onClick={() => setShowProgress(false)} aria-label="Cerrar progreso">×</button>
            </div>
            <p className="modal-summary">{totalDone} respondidas · {accuracy}% de precisión general · barras en porcentaje por dimensión</p>
            <div className="chart-controls" aria-label="Escala del gráfico">
              <span>Escala:</span>
              {CHART_MODES.map((chartOption) => (
                <button
                  key={chartOption.id}
                  className={chartMode === chartOption.id ? "active" : ""}
                  onClick={() => setChartMode(chartOption.id)}
                >
                  {chartOption.label}
                </button>
              ))}
            </div>
            <DimensionChart
              stats={chartStats}
              mode={chartMode}
              totalPresented={totalDone}
              totalAvailable={items.length}
            />
          </section>
        </div>
      )}
    </main>
  );
}
