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

  // Palette tuned for dark backgrounds: brighter, slightly less saturated
  const palette = [
    "#818cf8", "#34d399", "#fb7185", "#fbbf24", "#a78bfa",
    "#38bdf8", "#fb923c", "#22d3ee", "#c084fc", "#60a5fa",
    "#a3e635", "#f472b6", "#2dd4bf", "#f87171", "#4ade80",
    "#facc15", "#d4d4d8", "#94a3b8", "#5eead4", "#d8b4fe",
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
    // Dark theme: muted axis labels in zinc-400, gridlines in zinc-800
    Chart.defaults.color = "#a1a1aa";
    Chart.defaults.borderColor = "#27272a";
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    // Slightly lifted zinc-900 with a hairline ring for the tooltip
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(24, 24, 27, 0.95)";
    Chart.defaults.plugins.tooltip.borderColor = "rgba(63, 63, 70, 0.8)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.titleColor = "#fafafa";
    Chart.defaults.plugins.tooltip.bodyColor = "#e4e4e7";
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
