import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  // Where the app is served from: "/" locally, "/admin/" when it lives under the main site
  // (https://turavector.turacoz.com/admin/). Set VITE_BASE_PATH=admin in .env before `npm run build`.
  const basePath = (loadEnv(mode, process.cwd(), '').VITE_BASE_PATH || '').replace(/^\/+|\/+$/g, '');
  return {
    base: basePath ? `/${basePath}/` : '/',
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
    server: {
      port: 5174,
      strictPort: true,
      proxy: {
        '/api': 'http://localhost:8001',
        '/media': 'http://localhost:8001',
      },
    },
    preview: { port: 5174 },
  };
});
