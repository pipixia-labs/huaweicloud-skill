# Observability Readiness Playbook

## Goal

Confirm that a cloud resource can be observed through resource state, CES metrics, optional CES alarms, and LTS logs before declaring it healthy, idle, or ready for production.

## Standard Flow

1. Confirm the resource exists with the service-specific `Show*` or `List*` query.
2. Discover CES metric namespace, metric names, and dimensions:

```bash
python3 scripts/hcloud_observability_plan.py \
  --service ECS \
  --target-id <server-id> \
  --region=<region> \
  --project-id=<project-id> \
  --pretty
```

3. Review existing CES alarm rules and draft alarm intent without submitting:

```bash
python3 scripts/hcloud_ces_alarm_plan.py \
  --region=<region> \
  --project-id=<project-id> \
  --alarm-name <name> \
  --namespace <namespace> \
  --metric-name <metric-name> \
  --threshold <number> \
  --pretty
```

For ECS memory or disk alarms, read `references/playbooks/ces-metric-readiness.md` first. The CES alarm planner returns `metric_guidance` so the agent can distinguish basic `SYS.ECS` metrics from Agent-backed `AGT.ECS` metrics before proposing thresholds.

4. Discover LTS log groups and streams, then query a bounded time window:

```bash
python3 scripts/hcloud_lts_readonly.py \
  --region=<region> \
  --project-id=<project-id> \
  --log-group-id <group-id> \
  --log-stream-id <stream-id> \
  --start-time <start> \
  --end-time <end> \
  --keyword <keyword> \
  --pretty
```

## Boundaries

- CES alarm creation and notification changes are planner-only until a separate reviewed change flow exists.
- Empty metrics are not automatically a fault. Check region, namespace, dimension, period, time range, and collection delay first.
- Logs can contain sensitive application data. Keep queries narrow and summarize only the fields needed for the task.
