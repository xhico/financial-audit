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

  // Section accent colours — pair with the .tile.* tints
  const accents = {
    income:     "#10b981",  // emerald-500
    expense:    "#f43f5e",  // rose-500
    expenses:   "#f43f5e",
    savings:    "#8b5cf6",  // violet-500
    mortgage:   "#f59e0b",  // amber-500
    investment: "#06b6d4",  // cyan-500
    investments:"#06b6d4",
    accent:     "#6366f1",  // indigo-500
    neutral:    "#71717a",  // zinc-500
  };

  // Palette for varied category buckets (good contrast on white)
  const palette = [
    "#6366f1", "#10b981", "#f43f5e", "#f59e0b", "#8b5cf6",
    "#06b6d4", "#f97316", "#0ea5e9", "#a855f7", "#3b82f6",
    "#84cc16", "#ec4899", "#14b8a6", "#fb7185", "#22c55e",
    "#eab308", "#ea580c", "#475569", "#0d9488", "#9333ea",
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

  // Light theme defaults for Chart.js — zinc-500 labels, zinc-200 grid,
  // dark tooltips with white text
  function themeChartJs() {
    if (!window.Chart) return;
    Chart.defaults.font.family =
      '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = "#71717a";
    Chart.defaults.borderColor = "#e4e4e7";
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 12;
    Chart.defaults.plugins.tooltip.backgroundColor = "#18181b";
    Chart.defaults.plugins.tooltip.titleColor = "#ffffff";
    Chart.defaults.plugins.tooltip.bodyColor = "#e4e4e7";
    Chart.defaults.plugins.tooltip.titleFont = { weight: "600" };
    Chart.defaults.plugins.tooltip.bodySpacing = 4;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.padding = 16;
    Chart.defaults.elements.bar.borderRadius = 8;
    Chart.defaults.elements.line.borderWidth = 2.5;
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 5;
  }

  themeChartJs();

  return { fetchJson, formatCurrency, formatInt, colourFor, palette, accents, emptyMessage };
})();
