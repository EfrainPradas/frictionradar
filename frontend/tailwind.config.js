/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        orbital: {
          bg: '#050505',
          surface: '#0b0f12',
          elevated: '#101418',
          border: 'rgba(255,255,255,0.08)',
          'border-hover': 'rgba(255,255,255,0.12)',
          accent: '#bf9b30',
          'accent-dim': 'rgba(191,155,48,0.08)',
          'accent-glow': 'rgba(191,155,48,0.15)',
        },
        fr: {
          bg: 'var(--fr-bg)',
          paper: 'var(--fr-paper)',
          'paper-2': 'var(--fr-paper-2)',
          line: 'var(--fr-line)',
          'line-strong': 'var(--fr-line-strong)',
          ink: 'var(--fr-ink)',
          'ink-soft': 'var(--fr-ink-soft)',
          'ink-mute': 'var(--fr-ink-mute)',
          'ink-faint': 'var(--fr-ink-faint)',
          gold: 'var(--fr-gold)',
          'gold-soft': 'var(--fr-gold-soft)',
          'gold-tint': 'var(--fr-gold-tint)',
          blue: 'var(--fr-blue)',
          'blue-soft': 'var(--fr-blue-soft)',
          'blue-tint': 'var(--fr-blue-tint)',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'scan-line': 'scan-line 1.5s ease-in-out forwards',
        'signal-lock': 'signal-lock 400ms ease-out forwards',
        'amber-pulse': 'amber-pulse 3s ease-in-out infinite',
        'radar-sweep': 'radar-sweep 4s linear infinite',
        'ambient-drift': 'ambient-drift 60s ease-in-out infinite',
        'state-emerging': 'state-emerging 3s ease-in-out infinite',
        'state-accelerating': 'state-accelerating 2s ease-in-out infinite',
        'state-volatile': 'state-volatile 1.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}