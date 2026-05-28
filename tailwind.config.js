/*
 * Tailwind CSS configuration for the FinancialAudit dashboards.
 *
 * The content globs tell Tailwind which files to scan for class names so the
 * generated CSS only contains utilities that are actually used.
 */
module.exports = {
  content: [
    "./finance/templates/**/*.html",
    "./finance/static/finance/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
