import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const backendTarget = process.env.BACKEND_URL || process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/upload": {
        target: backendTarget,
        changeOrigin: true
      },
      "/ask": {
        target: backendTarget,
        changeOrigin: true
      },
      "/health": {
        target: backendTarget,
        changeOrigin: true
      },
      "/preview": {
        target: backendTarget,
        changeOrigin: true
      },
      "/datasets": {
        target: backendTarget,
        changeOrigin: true
      },
      "/auth": {
        target: backendTarget,
        changeOrigin: true
      },
      "/api": {
        target: backendTarget,
        changeOrigin: true
      }
    }
  }
})