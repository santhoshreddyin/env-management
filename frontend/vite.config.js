import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Forward API calls to the FastAPI backend during development.
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
    },
  },
});
