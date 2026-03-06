/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // HazardBrief カラーパレット: 赤を避けオレンジ〜黄色系でリスクを表現
        risk: {
          low: "#16a34a",      // green-600
          medium: "#d97706",   // amber-600
          high: "#ea580c",     // orange-600
          unknown: "#6b7280",  // gray-500
        },
      },
    },
  },
  plugins: [],
};
