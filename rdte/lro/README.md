# Ephemeral rendering service qualification

Standalone original two-sphere CPU ray-tracing fixture, not the Oneirifact product engine. Python 3.11+ standard library. It exercises asynchronous submission (202), per-run bearer authentication, bounded fixed inputs, idempotent replay, progress, fresh HTTP connections, real PNG generation/validation, and cancellation. The cancellation test uses a deliberate one-row gate; the image render uses real ray/sphere intersection and lighting without an artificial delay. It writes a PNG and JSON receipt, not an uptime or production readiness claim.

Run locally: `python3 rdte/lro/qualify.py --out /tmp/oneirifact-render-proof`.

For a Cloudflare Quick Tunnel test use the independently verified Linux amd64 cloudflared 2026.11.2 binary (SHA256 56f13335143ec0e22772963290683a84a04114a35ec64cbc794a4d39ff9bb8cf; upstream https://github.com/cloudflare/cloudflared/releases/tag/2026.11.2), then add `--cloudflared /absolute/path/to/cloudflared`. Tunnel lifetime is restricted to the test; no credentials, endpoint URL or private material are written to artifacts. The service accepts only two fixed test jobs, no arbitrary files or commands. Do not expose this fixture as a public rendering service. The workflow bounds execution and uploads only generated image and receipt. The client uses repeated HTTPS connections from the runner, not a geographically independent client or browser. No external state store, retry after runner loss, real Blender integration, production authorization, tenant isolation or GPU performance is established by this probe.

No private project source or CPE is used. This test is independent of GitHub Pages and requires no account or paid resources beyond the ordinary public repository CI entitlement.
