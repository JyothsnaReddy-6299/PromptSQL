import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/upload": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      },
      "/ask": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      },
      "/preview": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      }
    }
  }
})