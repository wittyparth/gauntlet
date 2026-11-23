# Third-party benchmark content

Importers in `tools/import_benchmarks/` read the upstream repositories below and write packs on
the user's machine. Packs derived from upstream data are not committed here: the importer needs a
checkout of the pinned upstream commit (a network download), so the data stays upstream and the
importer is what we ship. The pure tool ports in `tools/import_benchmarks/{tau,agentdojo}_handlers.py`
re-implement upstream tool behaviour and are covered by the licences below.

Licences verified from the upstream repositories on 2026-11-23 (CQ-P5).

## tau-bench (retail)

* Repository: https://github.com/sierra-research/tau-bench
* Pinned commit: 59a200c6d575d595120f1cb70fea53cef0632f6b (main on 2026-03-18, verified 2026-11-23)
* Licence: MIT, Copyright (c) 2024 Sierra

```text
MIT License

Copyright (c) 2024 Sierra

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## AgentDojo (banking and slack suites)

* Repository: https://github.com/ethz-spylab/agentdojo
* Pinned version: 0.1.35 (same pin as `attacks/NOTICES.md`)
* Licence: MIT, Copyright (c) 2024 Edoardo Debenedetti, Jie Zhang, Mislav Balunovic, Luca
  Beurer-Kellner, Marc Fischer, and Florian Tramèr; the full notice is in `attacks/NOTICES.md`
  and was re-verified against the upstream `LICENSE` on 2026-11-23.
