import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api':     { target: 'http://localhost:8000', changeOrigin: true },
      '/scan':    { target: 'http://localhost:8000', changeOrigin: true },
      '/stats':   { target: 'http://localhost:8000', changeOrigin: true },
      '/scanner': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
