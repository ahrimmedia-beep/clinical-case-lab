# web

Next.js 16 (App Router) frontend for Case Lab: catalogue, player, debrief, Studio, review and insights pages. It is the only caller of the `api` service; the typed server-only client lives in `src/lib/api/client.ts`.

Local dev: `pnpm install && pnpm dev` (serves built-in fixtures without `API_BASE_URL`), or `API_BASE_URL=http://localhost:8000 pnpm dev` against a running API. `pnpm typecheck`, `pnpm exec eslint .` and `pnpm test` (Vitest) are the checks CI runs.

See the repository [README.md](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the full system.
