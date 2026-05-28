/*
 * Author: xhico
 * Date: May 27, 2026
 * Shared dashboard helpers — fetch JSON, format currency, build charts.
 */

window.dashboard = (function () {
  // Sensible euro formatter for tabular display
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

  // Deterministic colour palette so categories keep their colour between pages
  const palette = [
    "#2563eb", "#dc2626", "#16a34a", "#f59e0b", "#7c3aed",
    "#0ea5e9", "#ea580c", "#10b981", "#a855f7", "#6366f1",
    "#84cc16", "#ec4899", "#14b8a6", "#f43f5e", "#22c55e",
    "#eab308", "#06b6d4", "#a16207", "#9333ea", "#475569",
  ];

  function colourFor(key) {
    // Hash the key into a stable palette index
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

  return { fetchJson, formatCurrency, formatInt, colourFor, palette, emptyMessage };
})();
