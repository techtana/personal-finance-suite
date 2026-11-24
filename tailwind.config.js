// Tailwind is compiled ahead of time into static/build/tailwind.css, so pages load one
// small stylesheet instead of compiling CSS in the browser. Rebuild after changing
// class names in templates or static JS:   python scripts/build_css.py
module.exports = {
  content: ['./templates/**/*.html', './static/*.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
