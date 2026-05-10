import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: '#3b5fc0',
          lt: '#eef1fb',
        },
        surface: '#ffffff',
        border: '#d1d5db',
        muted: '#5c6473',
        positive: '#166534',
        'positive-bg': '#bbf7d0',
        negative: '#991b1b',
        'negative-bg': '#fecaca',
      },
      fontFamily: {
        sans: ['Segoe UI', 'system-ui', 'sans-serif'],
      },
    },
  },
} satisfies Config
