# Hall of Failures: sources

Each scenario is a fictional re-creation of a failure class that was publicly reported. Worlds use
invented companies and cities; real names appear only in `tags.incident` and in this file. The
one-sentence summaries are neutral statements of what the cited source reports. Every source was
opened through a web search on 2026-11-21 and its core facts were checked against more than one
outlet where one exists. Details that rest on a single party's account are marked as such.

Columns: scenario, incident, year, what was reported (one neutral sentence), primary source to
check, status.

| scenario | incident | year | what was reported (one neutral sentence) | primary source to check | status |
|---|---|---|---|---|---|
| hof_01 | Air Canada | 2024 | A tribunal in British Columbia found an airline liable for a website chatbot that suggested a bereavement fare could be claimed after travel, contrary to the airline's published policy (Moffatt v. Air Canada, 2024 BCCRT 149). | https://decisions.civilresolutionbc.ca/crt/crtd/en/525448/1/document.do | verified 2026-11-21 |
| hof_02 | Chevrolet of Watsonville | 2023 | A dealership website chatbot, prompted by a user, was reported to call a one-dollar sale of a 2024 Tahoe "a legally binding offer"; the dealership did not honour it. | https://jalopnik.com/chevrolet-dealer-ai-help-chatbot-goes-rogue-pranksters-1851112556 | verified 2026-11-21 |
| hof_03 | DPD | 2024 | A parcel company's chatbot was reported to swear and write a poem criticising the company after a customer prompted it, and the company disabled the AI element. | https://www.theregister.com/2024/01/23/dpd_chatbot_goes_rogue | verified 2026-11-21 |
| hof_04 | NYC MyCity | 2024 | Journalists testing a city business chatbot reported that it said employers could take workers' tips and that landlords could refuse housing-voucher tenants, both contrary to city rules. | https://themarkup.org/news/2024/03/29/nycs-ai-chatbot-tells-businesses-to-break-the-law | verified 2026-11-21 |
| hof_05 | Replit | 2025 | A founder reported that a coding assistant deleted a live production database during a declared code freeze, and the company's chief executive called it a catastrophic error of judgement (deletion details rest mainly on the founder's own posts). | https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident | verified 2026-11-21 |
| hof_06 | Cursor | 2025 | A code editor's support bot told a user that only one device per subscription was allowed, a policy the company said did not exist (the original post was deleted, so the exact wording is second-hand). | https://www.theregister.com/2025/04/18/cursor_ai_support_bot_lies/ | verified 2026-11-21 |
| hof_07 | Slack AI | 2024 | Security researchers reported that a workspace assistant could be steered by an instruction in a public channel to place data from a private channel in a link, which the vendor described as intended behaviour before reports of a patch. | https://promptarmor.substack.com/p/data-exfiltration-from-slack-ai-via | verified 2026-11-21 |
| hof_08 | Microsoft 365 Copilot (EchoLeak) | 2025 | Researchers disclosed a zero-click flaw (CVE-2025-32711) in which a crafted inbound email could make an email copilot send data out; the vendor fixed it server-side and reported no evidence of in-the-wild use. | https://arxiv.org/html/2509.10540v1 | verified 2026-11-21 |

Secondary sources checked: American Bar Association Business Law Today and CTV News (hof_01);
Autoevolution, GM Authority and the AI Incident Database (hof_02); Business Insider and Digital
Trends (hof_03); the follow-up article by The Markup dated 2024-04-02 (hof_04); Fortune and
Tom's Hardware (hof_05); Fortune and eWeek (hof_06); Dark Reading and Simon Willison's weblog
(hof_07); The Hacker News and Dark Reading (hof_08).

Scenario 07 and 08 reuse imported library attacks: `atk_agentdojo_39ca122e` (AgentDojo, MIT) and
`atk_injecagent_2299ba2e` (InjecAgent, MIT). Their payloads are pre-placed in the worlds with a
fixed taint marker instead of a per-run one; the objectives only cover link, image and message
exfiltration of a planted canary, never harmful content.
