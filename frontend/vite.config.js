import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "AGRISHIELD_");
  const apiTarget = env.AGRISHIELD_DEV_API_TARGET;

  return {
    plugins: [react()],
    test: { environment: "jsdom" },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      ...(apiTarget && {
        proxy: {
          "/api": {
            target: apiTarget,
            changeOrigin: true,
          },
        },
      }),
    },
  };
});
