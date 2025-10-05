const stateEl = document.getElementById("state");
const scoreEl = document.getElementById("score");
const seatedEl = document.getElementById("seated");
const lastUpdatedEl = document.getElementById("last-updated");

const dailyProlongedEl = document.getElementById("daily-prolonged");
const dailyBreaksEl = document.getElementById("daily-breaks");
const dailyLongestEl = document.getElementById("daily-longest");
const dailyDateEl = document.getElementById("daily-date");
const dailySummaryEl = document.getElementById("daily-summary");

const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

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

  const rawScore = Number(score ?? 0);
  const scorePercent = Math.max(0, Math.min(100, rawScore * 100));
  scoreEl.textContent = `${scorePercent.toFixed(0)}%`;

  const seatedMinutes = metrics?.seated_minutes ?? 0;
  const breakMinutes = metrics?.break_minutes ?? 0;
  seatedEl.textContent = `${seatedMinutes.toFixed(1)} / ${breakMinutes.toFixed(1)} min`;

  lastUpdatedEl.textContent = `最近更新时间：${timeFormatter.format(now)}`;

  const dailyProlonged = Number(metrics?.daily_prolonged_minutes ?? 0);
  const dailyBreakCount = Number(metrics?.daily_break_count ?? 0);
  const dailyLongest = Number(metrics?.daily_longest_seated_minutes ?? 0);
  const dailyDate = metrics?.daily_date ?? null;
  const flowActive = Number(metrics?.flow_mode_active ?? 0) >= 0.5;
  const snoozeActive = Number(metrics?.snooze_active ?? 0) >= 0.5;
  const snoozeRemaining = Number(metrics?.snooze_remaining ?? 0);
  const quietActive = Number(metrics?.quiet_active ?? 0) >= 0.5;
  const quietRemaining = Number(metrics?.quiet_remaining ?? 0);
  const contextMode = metrics?.context_mode ?? "normal";
  const contextMessage = metrics?.context_message ?? "";
  const contextRemaining = Number(metrics?.context_remaining_minutes ?? 0);
  const contextSuppressed = Number(metrics?.context_suppressed_notifications ?? 0);

  if (dailyProlongedEl) {
    dailyProlongedEl.textContent = `${dailyProlonged.toFixed(1)} min`;
  }
  if (dailyBreaksEl) {
    dailyBreaksEl.textContent = dailyBreakCount.toFixed(0);
  }
  if (dailyLongestEl) {
    dailyLongestEl.textContent = `${dailyLongest.toFixed(1)} min`;
  }
  if (dailyDateEl) {
    const suffix = " · 仅统计进入久坐状态后的时长";
    dailyDateEl.textContent = dailyDate
      ? `统计日期：${dailyDate}${suffix}`
      : `统计日期：--${suffix}`;
  }

  const summaryPieces = [
    `今日久坐状态累计 ${dailyProlonged.toFixed(1)} 分钟`,
    `已起身休息 ${dailyBreakCount.toFixed(0)} 次`,
    `最长连续在座 ${dailyLongest.toFixed(1)} 分钟`,
  ];
  if (flowActive) {
    summaryPieces.push("当前处于心流模式，提醒已静默");
  }
  if (snoozeActive) {
    summaryPieces.push(`提醒延后中，剩余 ${snoozeRemaining.toFixed(1)} 分钟`);
  }
  if (quietActive) {
    summaryPieces.push(`处于静默时段，剩余 ${quietRemaining.toFixed(1)} 分钟`);
  }
  if (contextMode === "meeting") {
    summaryPieces.push(contextMessage || "会议模式，提醒已静音");
  } else if (contextMode === "presentation") {
    summaryPieces.push(contextMessage || "演示模式，提醒暂缓");
  } else if (contextMode === "post_meeting_pending") {
    const remain = Math.max(0, contextRemaining);
    const delayed = contextSuppressed > 0 ? `（已积累 ${contextSuppressed.toFixed(0)} 条提醒）` : "";
    summaryPieces.push(`会议刚结束 ${delayed}，${remain.toFixed(1)} 分钟后将统一提醒`);
  }
  if (contextMode === "sleep") {
    summaryPieces.push("系统睡眠中，提醒暂停");
  }
  if (dailySummaryEl) {
    dailySummaryEl.textContent = summaryPieces.join("，") + "。";
  }

}

fetchMetrics();
setInterval(fetchMetrics, 2000);
