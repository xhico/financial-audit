/*
 * Author: xhico
 * Date: May 27, 2026
 * Shared dashboard helpers — fetch JSON, format currency, theme Chart.js,
 * toggle light/dark mode.
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
    income:      "#10b981", // emerald-500
    expense:     "#f43f5e", // rose-500
    expenses:    "#f43f5e",
    savings:     "#8b5cf6", // violet-500
    mortgage:    "#f59e0b", // amber-500
    investment:  "#06b6d4", // cyan-500
    investments: "#06b6d4",
    accent:      "#6366f1", // indigo-500
    neutral:     "#71717a", // zinc-500
  };

  // Palette for varied category buckets (good contrast on both themes)
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

  function isDark() {
    return document.documentElement.classList.contains("dark");
  }

  // Pick chart colours from the current theme so axes and tooltips read well
  function chartTokens() {
    if (isDark()) {
      return {
        label: "#a1a1aa",  // zinc-400
        grid:  "#27272a",  // zinc-800
        tooltipBg:    "#fafafa",
        tooltipTitle: "#18181b",
        tooltipBody:  "#52525b",
      };
    }
    return {
      label: "#71717a",   // zinc-500
      grid:  "#e4e4e7",   // zinc-200
      tooltipBg:    "#18181b",
      tooltipTitle: "#ffffff",
      tooltipBody:  "#e4e4e7",
    };
  }

  // Apply (or re-apply) Chart.js defaults from the current theme. The goal
  // is a "sleek" look: no gridlines, no axis borders, sparse ticks, smooth
  // lines -- the data does the work, the chrome stays out of the way.
  function themeChartJs() {
    if (!window.Chart) return;
    const t = chartTokens();
    Chart.defaults.font.family =
      '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = t.label;
    Chart.defaults.borderColor = t.grid;

    // Tooltip: a small floating pill with strong contrast against the page
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 12;
    Chart.defaults.plugins.tooltip.backgroundColor = t.tooltipBg;
    Chart.defaults.plugins.tooltip.titleColor = t.tooltipTitle;
    Chart.defaults.plugins.tooltip.bodyColor = t.tooltipBody;
    Chart.defaults.plugins.tooltip.titleFont = { weight: "600" };
    Chart.defaults.plugins.tooltip.bodySpacing = 4;
    Chart.defaults.plugins.tooltip.displayColors = true;
    Chart.defaults.plugins.tooltip.boxWidth = 8;
    Chart.defaults.plugins.tooltip.boxHeight = 8;
    Chart.defaults.plugins.tooltip.usePointStyle = true;

    // Legend: subtle pill-style markers, generous spacing
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.padding = 16;

    // Bars + lines: rounded bars, smoother curves, no dots until hover
    Chart.defaults.elements.bar.borderRadius = 8;
    Chart.defaults.elements.bar.borderSkipped = false;
    Chart.defaults.elements.line.borderWidth = 2.5;
    Chart.defaults.elements.line.tension = 0.4;
    Chart.defaults.elements.line.cubicInterpolationMode = "monotone";
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 5;
    Chart.defaults.elements.point.hoverBorderWidth = 0;

    // Scales: the big visual change. Drop gridlines and axis borders;
    // every concrete scale (linear, category, ...) inherits from
    // `Chart.defaults.scale` so this one block covers all chart types.
    Chart.defaults.scale.grid.display = false;
    Chart.defaults.scale.border.display = false;
    Chart.defaults.scale.ticks.padding = 8;
    Chart.defaults.scale.ticks.maxTicksLimit = 5;
    Chart.defaults.scale.ticks.color = t.label;
  }

  // Force every Chart instance on the page to redraw with the new defaults
  function refreshCharts() {
    if (!window.Chart) return;
    document.querySelectorAll("canvas").forEach(canvas => {
      const chart = Chart.getChart(canvas);
      if (chart) chart.update("none");
    });
  }

  function toggleTheme() {
    const next = !isDark();
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("fa-theme", next ? "dark" : "light"); } catch (e) { /* ignore */ }
    themeChartJs();
    refreshCharts();
  }

  // Wire the toggle button (the inline head script already applied the initial theme)
  window.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("theme-toggle");
    if (btn) btn.addEventListener("click", toggleTheme);
  });

  themeChartJs();

  return {
    fetchJson, formatCurrency, formatInt, colourFor, palette, accents,
    emptyMessage, toggleTheme, themeChartJs, refreshCharts, isDark,
  };
})();
