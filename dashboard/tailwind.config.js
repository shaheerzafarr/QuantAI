/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0a0e17",
        card: "rgba(16, 24, 39, 0.75)",
        border: "rgba(255, 255, 255, 0.08)",
        accentGreen: "#10b981",
        accentRed: "#ef4444",
        accentBlue: "#3b82f6",
        accentPurple: "#8b5cf6",
      },
    },
  },
  plugins: [],
};
