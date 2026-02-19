/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        snow: {
          50: '#f0f7ff',
          100: '#e0efff',
          200: '#b9dfff',
          300: '#7cc5ff',
          400: '#36a8ff',
          500: '#0c8cf1',
          600: '#006fce',
          700: '#0058a7',
          800: '#044b89',
          900: '#0a3f71',
        },
      },
    },
  },
  plugins: [],
}
