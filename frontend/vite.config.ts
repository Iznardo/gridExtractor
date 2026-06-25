import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to 0.0.0.0 so the dev server is reachable from other devices on the
    // LAN (phone, another PC), not just from localhost.
    host: true,
    // The front talks to the API on its SAME origin (:5173) under /api, and Vite
    // proxies it to the real API (container published on localhost:8000).
    // This way there's no need to hardcode the host IP in the front or touch CORS:
    // the remote device's browser only ever sees a single origin.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
