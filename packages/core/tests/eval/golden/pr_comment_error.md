<!-- gauntlet-report -->
## Gauntlet: ERROR

| Metric | Value |
|---|---|
| Pass rate | n/a |
| Episodes counted | 0 |
| Cost per episode | $0.0010 |
| Latency p95 | n/a |

### Gates

| Gate | Status | Detail |
|---|---|---|
| run | fail | run status budget_exhausted |

[View the full run](https://gauntlet.example/runs/run_1)

<details><summary>Gate result JSON</summary>

```json
{
  "passed": false,
  "status": "error",
  "gates": [
    {
      "id": "run",
      "status": "fail",
      "value": null,
      "threshold": null,
      "detail": "run status budget_exhausted"
    }
  ]
}
```

</details>
