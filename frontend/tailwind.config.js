/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
      colors: {
        surface: { DEFAULT: '#FFFFFF', subtle: '#F7F8FA', muted: '#EEF1F4' },
        ink: { DEFAULT: '#171A1D', secondary: '#5E6872', muted: '#87919B' },
        border: { DEFAULT: '#DDE2E7', subtle: '#EDF0F3' },
        accent: { DEFAULT: '#198ACB', soft: '#E8F5FC' },
        success: { DEFAULT: '#17865D', soft: '#E7F5EF' },
        warning: { DEFAULT: '#A9630B', soft: '#FFF3DC' },
        danger: { DEFAULT: '#C43F3F', soft: '#FCEBEC' },
        code: { bg: '#111820', ink: '#DCE8F2', muted: '#687786' },
      },
    },
  },
  plugins: [],
};
