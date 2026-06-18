module.exports = {
  content: [
    './pages/**/*.{html,js}',
    './public/**/*.{html,js}',
  ],
  theme: {
    extend: {
      colors: {
        'q-bg': '#F4F4F5',
        'q-panel': '#FFFFFF',
        'q-border': '#E4E4E7',
        'q-text': '#18181B',
        'q-subtext': '#71717A',
        'q-up': '#EF4444',
        'q-down': '#10B981',
        'q-flat': '#A1A1AA',
        'q-primary': '#2563EB',
        'q-sidebar': '#FFFFFF',
        'q-side-text': '#52525B',
        'q-side-hover': '#F4F4F5',
        'q-side-active': '#18181B'
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"PingFang SC"', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        'q': '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
      }
    }
  }
};
