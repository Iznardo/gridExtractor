import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind a 0.0.0.0 para que el dev server sea accesible desde otros
    // dispositivos de la LAN (móvil, otro PC), no solo desde localhost.
    host: true,
    // El front habla con la API por su MISMO origen (:5173) bajo /api, y Vite
    // lo proxifica a la API real (contenedor publicado en localhost:8000).
    // Así no hay que hardcodear la IP del host en el front ni tocar CORS: el
    // navegador del dispositivo remoto solo ve un único origen.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
