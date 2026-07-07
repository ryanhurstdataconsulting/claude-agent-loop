---
name: engineering-delivery-metrics
description: Use when asked to measure engineering or developer productivity — instrumenting DORA metrics (deployment frequency, lead time for changes, change failure rate, time to restore service) from CI/CD and version-control data, designing a SPACE-framework-aligned developer-experience survey, or writing a leadership-facing DORA/delivery-metrics report or narrative. Triggers include "measure our delivery performance," "build a DevEx scorecard," "write a DORA report for leadership," a platform-adoption metric request (time-to-first-deploy, golden-path adoption rate), or a request to benchmark a team against DORA performance tiers.
---

# engineering-delivery-metrics

## Overview
Engineering delivery metrics covers the full pipeline from raw telemetry to leadership narrative: extracting the four DORA metrics from CI/CD and version-control data, pairing them with SPACE-framework qualitative signals and platform-adoption telemetry for a fuller developer-experience picture, and writing the resulting report at the altitude the audience needs. The one job it owns: turning delivery and developer-experience data into a report that informs decisions without being weaponized to evaluate individuals.

## When to use
- A request to "measure our delivery/engineering productivity" or benchmark a team against DORA performance tiers.
- Building a developer-experience (DevEx) survey or scorecard, distinct from pure output metrics.
- Measuring platform or golden-path adoption (time-to-first-deploy, template-adoption rate) after a platform-engineering investment.
- A leadership-facing report or narrative is due summarizing delivery performance for a period.
- A metrics dashboard shows a delivery-speed change and someone needs to determine whether it reflects a real productivity shift or an artifact of rising AI-generated commit volume.

## Workflow
1. **Extract the four DORA metrics from source data, not estimates:**
   - **Deployment frequency** — count of production deploys per unit time, from CI/CD deploy-stage logs.
   - **Lead time for changes** — commit-to-production-deploy elapsed time, from VCS commit timestamps joined to deploy timestamps.
   - **Change failure rate** — the share of deploys causing a production incident or requiring a hotfix/rollback, from incident/rollback records joined to deploy history.
   - **Time to restore service** — incident-open to incident-resolved elapsed time, from incident-tracking timestamps.
   Benchmark each against the published DORA performance tiers (Elite/High/Medium/Low), and state the benchmark tier plainly rather than leaving raw numbers for the reader to interpret unaided.
2. **Never stop at DORA alone — pair it with SPACE.** DORA measures throughput and stability; it says nothing about developer wellbeing, satisfaction, or perceived friction. Layer in SPACE-framework dimensions (Satisfaction, Performance, Activity, Communication/Collaboration, Efficiency/flow) so a delivery-metrics report cannot be misread as a complete productivity picture from output counts alone.
3. **Design the DevEx survey to complement, not duplicate, the telemetry.** Instrument what can be measured directly (golden-path adoption rate, time-to-first-deploy for a new service, CI queue wait time) and reserve survey questions for what only a human can report (perceived friction, satisfaction with tooling, cognitive load). A survey question asking what telemetry already answers wastes respondent goodwill.
4. **Flag the AI-generated-volume distortion explicitly.** Rising commit counts, PR counts, or deployment frequency can now reflect AI-assisted code generation volume rather than a genuine delivery-speed improvement — elevated raw output has been observed alongside *reduced* delivery stability on AI-heavy teams. Any report showing a throughput jump must check whether change-failure rate moved in the same period before calling it a win.
5. **Write the narrative at the requested altitude and never as an individual scorecard.** A team-level or org-level DORA report for delivery leadership is a different document from a service-level dashboard for an engineering manager; match scope to audience, but in every case make explicit that these are team/system-level indicators, not an individual-performance evaluation tool — using them to rank individual engineers is a well-documented DORA-methodology misuse, and the report should say so up front.
6. **Interpret trend shifts with a human in the loop.** Metric extraction and benchmark placement are mechanical; deciding whether a shift represents a real process change, a seasonal effect, or a data-quality artifact (a broken deploy-tagging convention, a merged pipeline that double-counts deploys) needs a person who knows the underlying system to sign off before the number goes into a leadership deck.

## Checklist / quality gate
- [ ] All four DORA metrics extracted from actual CI/CD and VCS data, not estimated or self-reported.
- [ ] Each metric is benchmarked against the published DORA performance tiers, not left as an unlabeled raw number.
- [ ] At least one SPACE-framework qualitative or platform-adoption signal is included alongside the DORA metrics — never a DORA-only report presented as full delivery-and-DevEx picture.
- [ ] Any throughput increase is checked against change-failure rate in the same period before being framed as an improvement.
- [ ] The report states explicitly that these are team/system-level indicators, not an individual-performance evaluation tool.
- [ ] A human with system context has reviewed any trend shift before it ships in a leadership-facing narrative.
- [ ] Survey questions (if any) cover what telemetry cannot measure directly, not a duplicate of the instrumented metrics.

## References
- DORA, "DORA metrics" guide — https://dora.dev/guides/dora-metrics/
- Forsgren et al., "The SPACE of Developer Productivity," ACM Queue (verify citation before use)
- Zylos Research, "Developer Productivity Metrics 2026" (AI-generated-volume distortion finding) — https://zylos.ai/research/2026-02-07-developer-productivity-metrics/
- Engineering Manager Tools, "DORA Metrics for Engineering Teams" — https://www.em-tools.io/frameworks/dora-metrics

## Composition
Feeds `status-report` with the delivery-metrics section of a periodic leadership update. Shares telemetry sources with `golden-path-template-authoring` (platform-adoption rate is often measured off the same scaffold-usage data) and pairs with `postmortem-generator`, since change-failure-rate and time-to-restore both draw on the same incident records. Hands the individual-sensitive portions (survey response synthesis, any people-level interpretation) to a human reviewer rather than automating them end to end.
