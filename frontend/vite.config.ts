import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('error', (_err, _req, res) => {
            if (res && 'writeHead' in res && typeof (res as import('http').ServerResponse).writeHead === 'function') {
              const serverRes = res as import('http').ServerResponse
              if (!serverRes.headersSent) {
                serverRes.writeHead(503, { 'Content-Type': 'application/json' })
                serverRes.end(JSON.stringify({ message: 'Backend initializing or reloading...' }))
              }
            }
          })
        },
      },
    },
  },
})
