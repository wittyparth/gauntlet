<!-- gauntlet-report -->
## Gauntlet: PASS

| Metric | Value |
|---|---|
| Pass rate | 100% (95% CI 57% to 100%) |
| Episodes counted | 5 |
| Versus baseline | No detectable change versus baseline: pass rate +0.0 points (95% CI -40.0 to -10.0). |
| pass^3 | 100% (95% CI 57% to 100%) |
| Cost per episode | $0.0010 (+11.1% versus baseline) |
| Latency p95 | 904 ms |

### Gates

| Gate | Status | Detail |
|---|---|---|
| regression | pass | no_detectable_change; delta +0.000 |
| security | skip | no baseline findings |

[View the full run](https://gauntlet.example/runs/run_1)

<details><summary>Gate result JSON</summary>

```json
{
  "passed": true,
  "status": "pass",
  "gates": [
    {
      "id": "regression",
      "status": "pass",
      "value": "no_detectable_change",
      "threshold": null,
      "detail": "delta +0.000"
    },
    {
      "id": "security",
      "status": "skip",
      "value": null,
      "threshold": null,
      "detail": "no baseline findings"
    }
  ]
}
```

</details>
