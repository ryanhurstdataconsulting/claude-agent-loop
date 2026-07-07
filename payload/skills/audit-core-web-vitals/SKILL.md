---
name: audit-core-web-vitals
description: Use when a performance regression, a low Lighthouse score, or a Core Web Vitals alert (LCP, INP, CLS) is reported for a web page or app. Provides a decision tree for diagnosing which metric regressed and why — bundle size, render-blocking resources, unoptimized images, layout shift, long main-thread tasks — plus a before/after measurement protocol so the fix is verified, not assumed. Triggers include "the site feels slow", a failing Lighthouse CI budget, a Real User Monitoring (RUM) dashboard alert, or a PR that noticeably increases bundle size.
---

# audit-core-web-vitals

## Overview
Diagnoses and fixes Core Web Vitals regressions (Largest Contentful Paint, Interaction
to Next Paint, Cumulative Layout Shift) using a metric-first decision tree, and proves
the fix worked with a measured before/after comparison. Owns the "why did this page get
slower/janky" diagnostic loop, not general application-performance profiling.

## When to use
- A Lighthouse CI budget check fails or a score drops below a set threshold.
- A Real User Monitoring dashboard flags a regression in field data (not just lab data).
- A user or stakeholder reports the page "feels slow" or "jumps around while loading."
- A PR review flags a meaningfully larger JavaScript or image bundle.
- Preparing a performance budget or baseline for a new page before launch.

## Workflow
1. **Measure first, diagnose second.** Capture a baseline with both a lab tool
   (Lighthouse, WebPageTest) and, if available, field data (Chrome UX Report, RUM).
   Lab and field data can disagree — a fast lab score with poor field CLS often points
   to a device/network segment the lab run doesn't represent (low-end mobile, slow 3G).
2. **Route by which metric regressed:**
   - **LCP (Largest Contentful Paint) high** → check, in order: is the LCP element
     render-blocked by CSS/JS that loads before it? Is it an image without
     `fetchpriority="high"` or `<link rel="preload">`? Is the server response itself
     slow (TTFB)? Is a web font blocking text render (`font-display: swap` missing)?
   - **INP (Interaction to Next Paint) high** → check for long main-thread tasks
     (>50ms) triggered by the interaction handler itself, unnecessary re-renders on
     every keystroke/click, and synchronous work that could move to
     `requestIdleCallback`, a Web Worker, or be deferred until after the next paint.
   - **CLS (Cumulative Layout Shift) high** → check for images/embeds/ads without
     explicit `width`/`height` (or `aspect-ratio`), web fonts causing a FOIT/FOUT
     reflow, and content injected above existing content (banners, cookie notices)
     without reserved space.
3. **Bisect bundle-size regressions** with a bundle analyzer (webpack-bundle-analyzer,
   `source-map-explorer`, or the framework's built-in equivalent) before guessing —
   confirm which dependency or route actually grew before proposing code-splitting.
4. **Prefer the smallest fix that addresses the root cause**, in this rough order of
   leverage: remove/defer unnecessary work > code-split/lazy-load > optimize the
   asset (image format/size, font subsetting) > add explicit reservation (dimensions,
   preload hints) > micro-optimize hot code paths. Don't reach for a rewrite when a
   `loading="lazy"` or a `preload` hint solves it.
5. **Re-measure with the same tool and conditions as the baseline** (same throttling
   profile, same device emulation) and report the delta per metric, not just "it's
   faster now."

## Checklist / quality gate
- [ ] A baseline measurement exists (lab and, where available, field data) before any
      fix was attempted.
- [ ] The regression is attributed to a specific, verified cause — not a guess.
- [ ] The fix targets the smallest sufficient change per the leverage order above.
- [ ] A post-fix measurement, run under the same conditions as the baseline, shows the
      metric back within budget.
- [ ] No metric was fixed at the expense of another (for example, deferring JS to fix
      INP that inadvertently delays LCP) without checking the trade-off.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend)
- [Frontend Developer Roadmap 2026 — GreatFrontEnd](https://www.greatfrontend.com/blog/frontend-developer-roadmap)

## Composition
A specialized instance of a general profile-and-fix-slow-request pattern, scoped to the
browser rendering path. Hands off to `scaffold-react-component-with-tests` when a fix
requires restructuring a component (for example, splitting a heavy component to enable
lazy-loading), and to a CI-pipeline-authoring skill to wire a Lighthouse budget check
into continuous integration so the regression doesn't recur silently.
