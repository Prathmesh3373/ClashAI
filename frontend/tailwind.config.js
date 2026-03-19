/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        arena: {
          bg: '#08070d',
          panel: '#12111a',
          panelAlt: '#181622',
          border: '#2c2740',
          text: '#f5f7fb',
          muted: '#9ca3af',
          gold: '#f8d46a',
        },
      },
      boxShadow: {
        glow: '0 20px 60px rgba(112, 72, 232, 0.18)',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(18px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        fadeUp: 'fadeUp 0.45s ease-out forwards',
      },
    },
  },
  plugins: [],
};
