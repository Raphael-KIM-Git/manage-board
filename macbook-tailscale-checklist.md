# MacBook Tailscale + Worker Checklist

## A. Tailscale client setup
- Install Tailscale on MacBook
- Sign in with the same account as the home PC
- Confirm the MacBook appears in the same tailnet
- Confirm the home PC appears as online

## B. Basic remote access check
- Open `http://<home-pc-tailscale-ip>:8765` from the MacBook browser
- Confirm the Raphael Agent Hub dashboard loads

## C. Worker-host preparation for later dispatch
- Confirm SSH is enabled on the MacBook
- Note the SSH username
- Note the hostname or Tailscale IP
- Create worker inbox directories:
  - `~/agent-hub/inbox/claude-code`
  - `~/agent-hub/inbox/openclaw`
  - `~/agent-hub/results`
  - `~/agent-hub/logs`

Suggested command:
```bash
mkdir -p ~/agent-hub/inbox/claude-code ~/agent-hub/inbox/openclaw ~/agent-hub/results ~/agent-hub/logs
```

## D. Information to send back to the hub setup
- Claude Code Worker host
- Claude Code Worker user
- OpenClaw Worker host (same MacBook이면 동일 가능)
- OpenClaw Worker user
- SSH port if non-default

## E. After that
- Update `/home/raphael/myproject/operations/config/workers.json`
- Re-test dispatch from the dashboard
