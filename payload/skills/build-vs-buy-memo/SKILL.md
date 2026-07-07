---
name: build-vs-buy-memo
description: Use when a team is deciding whether to build a capability in-house or buy/license a vendor, SaaS, or open-source solution — a new logging platform, an internal tool versus a subscription service, a custom auth flow versus a managed identity provider. Triggers include "should we build this or buy it," "evaluate vendor X versus building in-house," a procurement or budget review that needs a defensible recommendation, or a build-vs-buy `adr-authoring` decision that still needs its cost and risk analysis filled in. Produces a multi-year total-cost-of-ownership comparison, a risk matrix (lock-in, security, maintenance burden, key-person dependency), and a recommendation memo with confidence flagged on any assumed figures.
---

# build-vs-buy-memo

## Overview
Turns a build-or-buy question into a structured recommendation memo: a multi-year
total-cost-of-ownership comparison between the in-house and vendor paths, a risk
matrix scoring both against lock-in, security, and maintenance burden, and a named
recommendation with its confidence level made explicit. This skill owns the
comparison artifact end to end — gathering the cost and risk inputs, scoring both
paths on the same footing, and drafting the memo — but the purchase or build
commitment itself stays a human budget-owner's call.

## When to use
- A new capability is needed and there is a live choice between building it
  in-house and buying or licensing a vendor, SaaS, or open-source solution.
- A vendor renewal or subscription cost is being questioned against "could we
  just build this now?"
- A build-vs-buy `adr-authoring` decision needs its cost and risk comparison
  filled in before the record can be drafted.
- A budget or procurement review needs a defensible written recommendation, not
  just a gut call.
- Two teams have quietly diverged — one built, one bought — for the same job, and
  leadership wants a single consolidated recommendation.

## Workflow

**1. Frame the capability's strategic weight before comparing costs.** Is this a
core differentiator the product is judged on, or a supporting/commodity capability
every competitor also needs? Differentiating capabilities lean toward build (the
org needs full control and best-in-class quality); commodity capabilities lean
toward buy (someone else's core competency, not worth reinventing). State this
framing explicitly at the top of the memo — it sets the reader's expectations
before a single dollar figure appears.

**2. Gather cost inputs for both paths, marking each as sourced or estimated.**
- **Build:** engineering time in person-months (initial build plus a realistic
  ongoing maintenance load — commonly 15-20% of build effort per year), opportunity
  cost of what those engineers are not doing instead, and infrastructure to run it.
- **Buy:** license/subscription cost at the relevant seat count or usage tier,
  one-time implementation and integration cost, and ongoing vendor-management
  overhead (support contracts, admin time, contract renewal cycles).
Never present an estimated figure as if it were sourced — flag every assumption
inline so the reader can challenge it.

**3. Compute total cost of ownership (TCO) for both paths over the same horizon**
— three years is a common default, long enough to amortize build cost and reveal
subscription creep, short enough to still be a credible forecast. Line up
one-time and recurring costs side by side; a memo that only compares year-one
cost systematically favors "buy" because build's cost is front-loaded and buy's
is deferred.

**4. Build a risk matrix.** At minimum, score both paths against:
- **Lock-in / exit cost** — how hard is it to leave this vendor, or to hand off
  this in-house system to a different team, later?
- **Data portability** — can the org get its data out in a usable format on exit?
- **Security and compliance posture** — vendor's certifications and track record
  versus the team's own security practice for a built system.
- **Maintenance burden** — who is on the hook when it breaks at 2 a.m.?
- **Key-person dependency (build)** — does this create a single point of
  organizational failure if the builder leaves?
- **Vendor viability (buy)** — funding stability, roadmap direction, how replaceable
  the vendor is if it is acquired, sunsets the product, or raises prices sharply.

**5. Score non-cost criteria.** Time-to-value (buy is almost always faster to a
first working version), whether the team already has the skill set the build path
requires, and integration complexity with the existing stack.

**6. Draft the recommendation memo with an explicit call, not just a comparison
table.** State the recommendation in one sentence, then the reasoning, then the
supporting TCO and risk detail. A memo that lists pros and cons for both sides and
stops short of a recommendation has not done the job it was asked to do — but
attach a confidence level (high/medium/low) so the reader knows how much weight
the underlying figures can bear.

**7. Route the actual commitment to a human.** The agent drafts and recommends;
budget approval and vendor contract terms are a human decision, and the memo
should say so rather than imply the recommendation is self-executing.

**Common gotchas:**
- Sunk-cost or "it would be fun to build" bias creeping into the build-path
  estimate — keep the framing in step 1 explicit so it surfaces this.
- Using a vendor's list price instead of the actual negotiated price at the org's
  likely usage tier — list price is a starting point for negotiation, not a cost.
- Omitting the buy path's integration cost, which can rival the license cost for
  a complex system.
- Comparing only year-one cost, which structurally favors buy (see step 3).
- Treating the decision as permanent — note a revisit trigger (contract renewal,
  a major usage-tier jump, a team-size change) so the memo isn't read as final.

## Checklist / quality gate
- [ ] The capability's strategic weight (differentiator vs. commodity) is stated
      explicitly before the cost comparison.
- [ ] TCO is computed for both paths over the same multi-year horizon, with every
      figure marked sourced or estimated.
- [ ] The risk matrix covers lock-in, data portability, security/compliance,
      maintenance burden, and both key-person (build) and vendor-viability (buy)
      risk.
- [ ] Non-cost criteria — time-to-value, existing skill fit, integration
      complexity — are addressed, not just cost.
- [ ] The memo states an explicit recommendation with a confidence level, not
      just a side-by-side comparison.
- [ ] A revisit trigger is named so the recommendation isn't read as permanent.
- [ ] The memo is routed to a human budget-owner for the actual commitment.

## References
- [CTO Executive Insights — VP of Engineering Decision Authority at 100+ Employees](https://ctoexecutiveinsights.com/blog/vp-of-engineering-decision-authority-at-100-employees)

## Composition
- Hands off to `adr-authoring` when the build-or-buy call is architecturally
  significant enough to warrant a permanent decision record — this memo supplies
  the cost/risk section, the ADR supplies the durable rationale document.
- Pairs with `tech-radar-update` — an option moving from Assess to Trial on the
  radar is a common trigger for a build-vs-buy evaluation, and a completed memo
  is evidence for the radar entry's next-cycle rationale.
- Feeds `status-report` or `executive-report-narrative-draft` when the
  recommendation needs to be summarized for a leadership or board update.
