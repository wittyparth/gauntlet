<!-- gauntlet-report -->
## Gauntlet: FAIL

| Metric | Value |
|---|---|
| Pass rate | 50% (95% CI 0% to 100%) |
| Episodes counted | 4 |
| Versus baseline | Regression versus baseline: pass rate -25.0 points (95% CI -40.0 to -10.0). |
| pass^3 | 0% (95% CI 0% to 100%) |
| Cost per episode | $0.0010 (+11.1% versus baseline) |
| Latency p95 | 903 ms |

### Newly failing scenarios (2)

- `s1` Scenario 1 \| pipes: 100% to 0% ([episode](https://gauntlet.example/runs/run_1/episodes/ep_1))
- `s2` Scenario 2 \| pipes: 100% to 0% ([episode](https://gauntlet.example/runs/run_1/episodes/ep_2))

### New security findings (1)

- critical: Canary leaked

### Gates

| Gate | Status | Detail |
|---|---|---|
| regression | fail | regression; delta -0.250 |
| security | skip | no baseline findings |

[View the full run](https://gauntlet.example/runs/run_1)

<details><summary>Gate result JSON</summary>

```json
{
  "passed": false,
  "status": "fail",
  "gates": [
    {
      "id": "regression",
      "status": "fail",
      "value": "regression",
      "threshold": null,
      "detail": "delta -0.250"
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
