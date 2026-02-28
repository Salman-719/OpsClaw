/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fef7ee',
          100: '#fdedd3',
          200: '#f9d6a5',
          300: '#f5b86d',
          400: '#f09032',
          500: '#ed7512',
          600: '#de5b08',
          700: '#b84309',
          800: '#93360e',
          900: '#772e0f',
        },
      },
    },
  },
  plugins: [],
}
