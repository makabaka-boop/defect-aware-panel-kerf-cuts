import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 本地开发：/api 代理到 FastAPI；容器内由 nginx 同源反代
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
