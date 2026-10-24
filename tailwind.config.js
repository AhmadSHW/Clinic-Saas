/** @type {import('tailwindcss').Config} */
module.exports = {
  // Python files are scanned too, because some classes come from template tags
  content: [
    "./templates/**/*.html",
    "./*/templates/**/*.html",
    "./*/templatetags/*.py",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "IBM Plex Sans Arabic", "ui-sans-serif", "system-ui", "sans-serif"],
        arabic: ["IBM Plex Sans Arabic", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
        lift: "0 12px 32px -12px rgba(15, 23, 42, 0.18)",
      },
      keyframes: {
        "toast-in": { from: { opacity: "0", transform: "translateY(-8px)" }, to: { opacity: "1", transform: "none" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "pop-in": { from: { opacity: "0", transform: "scale(.96)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: {
        "toast-in": "toast-in .25s ease-out",
        "fade-in": "fade-in .15s ease-out",
        "pop-in": "pop-in .18s ease-out",
      },
    },
  },
  plugins: [],
};
