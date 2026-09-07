import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same-machine default; override for Docker Compose, where "localhost"
    // from inside the frontend container wouldn't reach a separate backend
    // container -- there it's set to the backend service's container name
    // (e.g. http://backend:8000, see docker-compose.yml).
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
