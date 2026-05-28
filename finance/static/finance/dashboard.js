/*
 * Author: xhico
 * Date: May 27, 2026
 * Shared dashboard helpers — fetch JSON, format currency, theme Chart.js.
 */

window.dashboard = (function () {
  // Sensible euro formatters for tabular display
  const eurFmt = new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
  const eurFmtCents = new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  });
  const intFmt = new Intl.NumberFormat("en-IE");

  // Palette aligned with the CSS tokens, picked to read well on white
  const palette = [
    "#6366f1", "#10b981", "#ef4444", "#f59e0b", "#8b5cf6",
    "#0ea5e9", "#f97316", "#06b6d4", "#a855f7", "#3b82f6",
    "#84cc16", "#ec4899", "#14b8a6", "#f43f5e", "#22c55e",
    "#eab308", "#a16207", "#475569", "#0d9488", "#9333ea",
  ];

  function colourFor(key) {
    // Stable palette index from a simple hash of the key string
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
    return palette[Math.abs(h) % palette.length];
  }

  async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`${url} -> ${response.status}`);
    return response.json();
  }

  function formatCurrency(amount, withCents = false) {
    const fmt = withCents ? eurFmtCents : eurFmt;
    return fmt.format(amount || 0);
  }

  function formatInt(n) {
    return intFmt.format(n || 0);
  }

  function emptyMessage(container, message) {
    container.innerHTML = `<p class="empty">${message}</p>`;
  }

  // Apply project-wide chart defaults once Chart.js is on the page
  function themeChartJs() {
    if (!window.Chart) return;
    Chart.defaults.font.family =
      '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = "#64748b";
    Chart.defaults.borderColor = "#e5e8ef";
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(15, 23, 42, 0.92)";
    Chart.defaults.plugins.tooltip.titleFont = { weight: "600" };
    Chart.defaults.plugins.tooltip.bodySpacing = 4;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.padding = 16;
    Chart.defaults.elements.bar.borderRadius = 6;
    Chart.defaults.elements.line.borderWidth = 2;
    Chart.defaults.elements.point.radius = 3;
    Chart.defaults.elements.point.hoverRadius = 5;
  }

  // The dashboard.js script is deferred and runs after chart.umd.min.js,
  // so Chart is defined when this IIFE executes
  themeChartJs();

  return { fetchJson, formatCurrency, formatInt, colourFor, palette, emptyMessage };
})();
