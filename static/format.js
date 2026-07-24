function dayCountLabel(days) {
  return `${days} 天`;
}

// Shared by runs.js (every past run) and trips.js (saved trips, which can
// now be infeasible/failed_max_iterations too, not just done -- see
// viewer.js's showResult for why).
const STATUS_LABELS = {
  done: "已完成",
  infeasible: "不合適",
  no_results: "無結果",
  failed_max_iterations: "已用完嘗試次數",
  in_progress: "進行中",
};
