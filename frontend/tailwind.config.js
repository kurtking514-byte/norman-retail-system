/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Sign red from the shop poster
        brand: {
          50: '#fdf3f1',
          100: '#fbe3df',
          200: '#f6c4bc',
          300: '#ee988b',
          400: '#e3624f',
          500: '#d93a26',
          600: '#c8251a',
          700: '#a61d15',
          800: '#861a14',
          900: '#6b1712',
        },
        // Warm near-black with a hint of the woven-cloth maroon
        ink: {
          700: '#3a2c2a',
          800: '#2a201f',
          900: '#1c1514',
        },
        // Rice-terrace green
        terrace: {
          50: '#f1f7ec',
          100: '#ddeed2',
          200: '#c3e0b0',
          500: '#4f8a2e',
          600: '#3f7224',
          700: '#2f5a1b',
          800: '#24461a',
        },
      },
      fontFamily: {
        sans: ['Barlow', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Barlow Condensed"', 'Barlow', 'ui-sans-serif', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
