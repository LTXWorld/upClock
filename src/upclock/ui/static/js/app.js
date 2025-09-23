const stateEl = document.getElementById("state");
const scoreEl = document.getElementById("score");
const seatedEl = document.getElementById("seated");
const lastUpdatedEl = document.getElementById("last-updated");

const activitySumEl = document.getElementById("activity-sum");
const normalizedEl = document.getElementById("normalized-activity");
const seatedMinutesEl = document.getElementById("seated-minutes");
const breakMinutesEl = document.getElementById("break-minutes");
const presenceConfidenceEl = document.getElementById("presence-confidence");
const postureScoreEl = document.getElementById("posture-score");
const postureStateEl = document.getElementById("posture-state");

const formatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const ctx = document.getElementById("trend-chart");
const HISTORY_LIMIT = 150;

const ChartLib = window.Chart || null;
const chart = ChartLib && ctx
  ? new ChartLib(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Score",
            data: [],
            borderColor: "#4f7cff",
            backgroundColor: "rgba(79, 124, 255, 0.1)",
            tension: 0.35,
            fill: true,
          },
          {
            label: "Seated (min)",
            data: [],
            borderColor: "#f7b851",
            backgroundColor: "rgba(247, 184, 81, 0.08)",
            tension: 0.35,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        animation: false,
        responsive: true,
        scales: {
          y: {
            suggestedMin: 0,
            suggestedMax: 1,
            ticks: {
              callback: (value) => Number(value).toFixed(1),
            },
          },
          y1: {
            position: "right",
            suggestedMin: 0,
            grid: {
              drawOnChartArea: false,
            },
          },
        },
        plugins: {
          legend: {
            labels: {
              color: "#cfd2dc",
            },
          },
        },
      },
    })
  : null;

if (!ChartLib) {
  console.warn("Chart.js 未加载，将仅显示基础卡片");
}

const STATE_LABELS = {
  ACTIVE: "活跃",
  SHORT_BREAK: "短暂休息",
  PROLONGED_SEATED: "久坐",
};

function applyStateClass(state) {
  stateEl.classList.remove("state-active", "state-short_break", "state-prolonged_seated");
  if (!state) return;
  const key = state.toLowerCase();
  const className = `state-${key}`;
  stateEl.classList.add(className);
}

async function fetchMetrics() {
  try {
    const response = await fetch("/metrics", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    console.debug("metrics", payload);
    updateView(payload);
  } catch (error) {
    console.error("获取指标失败", error);
    lastUpdatedEl.textContent = `获取数据失败：${error}`;
  }
}

function updateView(data) {
  const { score, state, metrics } = data;
  const now = new Date();

  stateEl.textContent = STATE_LABELS[state] ?? state ?? "UNKNOWN";
  applyStateClass(state);

  scoreEl.textContent = Number(score).toFixed(3);

  const seatedMinutes = metrics?.seated_minutes ?? 0;
  const breakMinutes = metrics?.break_minutes ?? 0;
  seatedEl.textContent = `${seatedMinutes.toFixed(1)} / ${breakMinutes.toFixed(1)} min`;

  lastUpdatedEl.textContent = `最近更新时间：${timeFormatter.format(now)}`;

  activitySumEl.textContent = formatter.format(metrics?.activity_sum ?? 0);
  normalizedEl.textContent = Number(metrics?.normalized_activity ?? 0).toFixed(3);
  seatedMinutesEl.textContent = seatedMinutes.toFixed(3);
  breakMinutesEl.textContent = breakMinutes.toFixed(3);
  presenceConfidenceEl.textContent = Number(metrics?.presence_confidence ?? 0).toFixed(2);
  postureScoreEl.textContent = Number(metrics?.posture_score ?? 0).toFixed(2);
  postureStateEl.textContent = metrics?.posture_state ?? "unknown";

  appendHistory(now, Number(score || 0), Number(seatedMinutes));
}

function appendHistory(timestamp, score, seatedMinutes) {
  if (!chart) return;

  const label = timeFormatter.format(timestamp);
  const labels = chart.data.labels;
  const scoreData = chart.data.datasets[0].data;
  const idleData = chart.data.datasets[1].data;

  labels.push(label);
  scoreData.push(score);
  idleData.push(seatedMinutes);

  if (labels.length > HISTORY_LIMIT) {
    labels.shift();
    scoreData.shift();
    idleData.shift();
  }

  chart.update();
}

fetchMetrics();
setInterval(fetchMetrics, 2000);
