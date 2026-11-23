# CI gate

`gauntlet gate` turns a finished run into pass, fail or error against a gates file, and exits accordingly (0 passed, 1 a gate failed, 2 usage error, 3 platform failure).

```sh
gauntlet run packs/ecommerce --target agent.yaml --suite smoke --budget-usd 1 --out run/
gauntlet gate --run run/ --baseline baseline-run/ --gates gates.yaml --md-out comment.md
```

`--run` and `--baseline` take a local run directory or, with `--api-url` and `GAUNTLET_API_KEY`, a server run id. `--md-out` writes a pull-request comment. Gates cover pass-rate floors, regressions against the baseline and new critical findings; only calibrated rubrics may gate. `gauntlet impact` selects just the scenarios a change can affect, to keep CI runs small. Options: [CLI reference](../reference/cli.md).
