# Deployment

ARGUS has a React frontend, a FastAPI core, a PyTorch graph service and an
optional infrastructure replay service. Deploy all four for the complete demo.
The current backend uses SQLite and an in-process WebSocket broadcaster: run
one core process with persistent disk. A separate database service is not
required for a small assignment demo.

## One server with Docker Compose

This requires the fewest application changes. Use a Linux host with Docker
Compose v2. Size memory for the CPU PyTorch service and measure the actual demo;
this repository does not establish a minimum hosting-plan capacity.

```bash
git clone https://github.com/pratyushdeosingh/ARGUS_CSI.git
cd ARGUS_CSI
docker compose up --build -d --wait --wait-timeout 120
```

Leave `VITE_API_BASE_URL` empty in the root `.env`. The dashboard's Nginx serves
the UI and proxies `/api/` and `/ws/` to the core. A remote browser therefore
uses the server's origin instead of trying to contact its own localhost.
Dashboard entry point: `http://YOUR_SERVER:5173`.

For HTTPS, place the dashboard behind your host's TLS reverse proxy; preserve
WebSocket Upgrade headers. Restrict inbound detector/core ports 8000–8002 at
the host firewall; only the dashboard/proxy needs public access in this setup.
The `argus-runtime` volume stores payments, events, cases, notes and audits.
`docker compose down` preserves it. `docker compose down -v` deletes it.
Back up that volume before replacing the server.

## Vercel frontend with a separately hosted backend

1. Deploy the Python services on a container host with persistent disk. The
   core must reach `GRAPH_DETECTOR_URL` and `EBPF_DETECTOR_URL` over its private
   network. Set `ARGUS_DETECTOR_MODE=required`, `ARGUS_EBPF_MODE=replay`, and
   `ARGUS_DB_PATH` to a file inside the core's persistent disk mount.
2. Give the core a public HTTPS origin, for example `https://api.example.com`.
   Its reverse proxy must route `/api/` and `/ws/` to the same single core
   process. Ensure the graph detector timeout covers your measured workload.
3. Import the GitHub repository in Vercel. Set **Root Directory** to `frontend`,
   framework to **Vite**, build to `pnpm build`, output to `dist`, Node to 22.
   The committed `frontend/vercel.json` supplies the static build settings.
4. In Vercel project environment variables, set
   `VITE_API_BASE_URL=https://api.example.com` (no `/api` suffix). Redeploy after
   changing it: Vite embeds this value at build time. HTTPS selects WSS for the
   dashboard's WebSocket connection.
5. On the backend, set
   `ARGUS_ALLOWED_ORIGINS=https://your-project.vercel.app` and restart it. List
   multiple exact frontend origins separated by commas if necessary. Avoid
   granting every preview deployment wildcard access.
6. Verify detector health, run synthetic payments, open a saved case, add a
   note, download its draft report, then restart the core and reopen the case.

Uploading the whole repository to Vercel does not provision the graph service
or make the local SQLite database persistent. An all-Vercel architecture would
require a durable external database and cross-instance event distribution,
plus validating the PyTorch workload against runtime limits. That migration is
outside this submission release. See Vercel's
[Python API hosting guidance](https://vercel.com/i/where-to-host-python-api)
and [WebSocket state guidance](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections).

## Hosting boundary

This is a synthetic assignment prototype. Use synthetic inputs on a hosted
demo. Analyst names are caller supplied; authentication/roles and real payment
controls are not implemented. Restrict reviewer access using your hosting
provider or reverse proxy. No cloud deployment or paid resource is provisioned
by these configuration files.
