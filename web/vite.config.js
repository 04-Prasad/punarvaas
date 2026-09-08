import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      // Forward all /api requests to the FastAPI backend.
      // `api.js` uses BASE = "/api", so this is transparent to the frontend.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});