# Frontend (React + Vite)

```bash
npm install
npm run dev      # http://localhost:5173  (proxies /api to the backend on :8000)
npm run lint
npm run build    # production files in dist/ (served by Nginx in Docker)
```

Structure:

```
src/
  main.jsx, App.jsx      app shell, hash routing, browser notifications
  api.js                 fetch wrapper (shows backend "hint" messages)
  navigation.js          sidebar entries
  hooks/usePolling.js    refresh data every N seconds, pauses in hidden tabs
  hooks/useToast.jsx     action confirmations
  components/            charts (hand-written SVG), log viewer, AI drawer, UI primitives
  pages/                 one file per module (Dashboard, System, CICD, Containers,
                         Infrastructure, Assistant, Logs, Alerts)
  styles.css             all styling (CSS variables, no CSS framework)
```
