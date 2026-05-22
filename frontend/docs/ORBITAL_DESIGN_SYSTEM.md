# FrictionRadar — Organizational Intelligence Platform Design System

**Version:** 2.0  
**Codename:** ORBITAL  
**Date:** 2026-05-18  

---

> "The operating system for organizational intelligence."

---

## 0. Design Philosophy

FrictionRadar is not a dashboard. It is a **command console** for detecting hidden operational friction inside companies. Every pixel, every transition, every glow exists to surface signal — not decoration.

**Core principles:**

1. **Evidence over assertion.** Never state a conclusion without showing the evidence chain that produced it. The UI is a conviction pipeline, not a claim machine.
2. **Signal density with visual clarity.** High information density is a feature, not a bug. Clutter is the enemy. Density with rhythm is mastery.
3. **Restraint communicates trust.** Motion exists to reveal structure, not to entertain. A pulse on a radar node means "new signal arrived." A scan sweep means "the system is working." Nothing moves without purpose.
4. **Temporal intelligence is narrative.** Companies are stories unfolding. The interface must reveal narrative arcs — emergence, acceleration, stabilization, decline — not just static snapshots.
5. **Classified, not gamified.** The aesthetic borrows from intelligence systems, not gaming. Amber glow means "attention," not "achievement unlocked." Dark backgrounds mean "focus," not "hacker aesthetic."

---

## 1. Global Experience

### 1.1 Application Shell

The shell is a fixed-layout frame with three persistent zones:

```
┌─────────────────────────────────────────────────────────────────┐
│ ◆ FRICTIONRADAR        [company search]      [temporal] [user]  │  ← Header bar (48px)
├──────┬──────────────────────────────────────────────────────────┤
│      │                                                          │
│ N    │                                                          │
│ A    │                    CONTENT AREA                          │
│ V    │                                                          │
│      │                                                          │
│ 56px │                                                          │
│      │                                                          │
├──────┴──────────────────────────────────────────────────────────┤
│ STATUS BAR — signal count · last scan · confidence · temporal  │  ← 28px
└─────────────────────────────────────────────────────────────────┘
```

**Header bar:** Fixed 48px. Background `#0b0f12`. Left: logo mark + wordmark. Center: company search with typeahead. Right: temporal scope selector, user avatar.

**Navigation rail:** Fixed 56px wide. Background `#080b0e`. Vertically stacked icon buttons with label on hover. Active state: amber glow left border.

**Status bar:** Fixed 28px at bottom. Background `#050505`. Monospace text. Real-time metrics: signal count, last scan timestamp, current confidence level, temporal state indicator.

**Content area:** Background `#050505`. Subtle dot grid overlay at 24px intervals, `rgba(255,255,255,0.02)`, visible only on large displays (>1440px). This grid creates spatial rhythm without distraction.

### 1.2 Navigation System

Navigation is **spatial, not hierarchical.** Users think "I'm looking at Acme Corp's temporal intelligence," not "I'm on page 3 of a dashboard."

**Primary navigation items:**

| Icon | View | Description |
|------|------|-------------|
| ◎ | Radar | Organizational radar visualization |
| ⟐ | Company | Company command center (overview + verdict) |
| ⟡ | Timeline | Temporal intelligence timeline |
| ⊛ | Signals | Signal constellation view |
| ⬡ | Intelligence | Analysis + strategic interpretation |
| ⟡ | Directory | Company list / search |

**Transitions between views:** Views do not "page swap." They **morph.** The radar polygon contracts into the company card. The timeline slides laterally. The constellation zooms. All transitions use `cubic-bezier(0.16, 1, 0.3, 1)` — fast start, gentle settle.

### 1.3 Company Switching

The header search is a **command palette** activated by `Cmd+K`:

1. User types company name or domain.
2. Results appear in a floating panel with: company name, domain, current temporal state indicator (colored dot), dominant friction category, confidence band.
3. Selecting a company triggers a **context transition:** the entire content area crossfades (300ms) while the radar/constellation morphs to the new company's geometry.

### 1.4 Temporal Navigation

A scope selector in the header controls the temporal window:

```
[7D] [30D] [90D] [180D]
```

Active scope: amber underline. Changing scope triggers a **temporal scrub** — the timeline compresses/expands, the radar polygon reshapes, deltas recalculate. A 200ms crossfade with a subtle amber pulse at the scope boundary.

### 1.5 Background Motion System

The background is never truly static, but never distracting.

**Atmosphere layer:** A single radial gradient centered at `(50%, 40%)` with color `rgba(191, 155, 48, 0.03)` that slowly drifts over 60 seconds in a Lissajous curve. This creates a living warmth without distraction.

**Grid overlay:** Static dot grid at `rgba(255,255,255,0.015)`. On 4K displays, dots become barely perceptible depth markers.

**Scan line:** When a new analysis is triggered, a horizontal amber line sweeps top-to-bottom over 1.5s (`rgba(191, 155, 48, 0.08)`), then fades. This signals "the system is processing."

### 1.6 Loading States

Loading is not a spinner. It is a **scan sequence:**

1. The content area shows a subtle amber scan line (1.5s sweep).
2. Skeleton elements appear with a stagger: each section fades in 150ms after the previous.
3. When data arrives, each section does a **signal lock** animation: a brief amber pulse on the section border (200ms), then content appears.

No skeleton stays visible for more than 5 seconds. After 5s, show "Signal acquisition in progress" with a retry option.

### 1.7 Cinematic Transitions

| Transition | Trigger | Duration | Easing | Effect |
|-----------|---------|----------|--------|--------|
| View morph | Nav click | 400ms | `cubic-bezier(0.16, 1, 0.3, 1)` | Content crossfades, radar reshapes |
| Company switch | Search select | 300ms | `ease-out` | Full crossfade, amber pulse |
| Scope change | Temporal nav | 200ms | `ease-in-out` | Timeline scrub, data reflow |
| Section reveal | Data loaded | 300ms | `spring(1, 80, 10)` | Fade in + 4px upward translate |
| Signal arrive | New data | 600ms | `ease-out` | Node pulse, amber ring expand |
| Alert emerge | State change | 500ms | `spring(1, 100, 12)` | Slide from right, amber glow |
| Section collapse | User toggle | 250ms | `ease-in-out` | Height animate, opacity fade |

---

## 2. Organizational Radar

### 2.1 Concept

The radar is a **multi-axis polygon chart** rendered on a circular canvas. It visualizes 8 organizational dimensions simultaneously, with temporal behavior showing as shape evolution.

The radar is NOT a static chart. It breathes. It pulses. It reveals.

### 2.2 Axes

| Axis | Label | Source | Range |
|------|-------|--------|-------|
| P | Pressure | `hiring_pressure` from verdict | low→high |
| C | Concentration | `function_concentration` KPI | low→high |
| R | Readiness | `positioning_readiness` KPI (inverted: high readiness = low radar value) | low→high |
| Cv | Coverage | `extraction_coverage` KPI | low→high |
| Cx | Complexity | `distinct_signal_types / max_possible` | low→high |
| SD | Signal Density | `scored_signals / total_signals` | low→high |
| TS | Temporal Stability | inverse of `temporal_state` volatility | volatile→stable |
| CF | Confidence | `confidence` level mapped to numeric | none→high |

### 2.3 Visual Specification

**Canvas:** 400×400px minimum, scales to container. Background: `#080b0e`.

**Grid rings:** 3 concentric rings at 33%, 66%, 100% of radius. Color: `rgba(255,255,255,0.06)`. Stroke: 0.5px.

**Axis lines:** 8 lines from center to perimeter. Color: `rgba(255,255,255,0.08)`. Dashed pattern: `4px gap 4px`.

**Axis labels:** Positioned outside the perimeter. Font: `text-[10px] font-medium tracking-widest uppercase text-gray-500`. Each label has a small colored dot (amber for elevated, green for stable, red for critical).

**Data polygon:** The primary shape. Fill: `rgba(191, 155, 48, 0.08)`. Stroke: `rgba(191, 155, 48, 0.6)`. Stroke width: 1.5px. Corner radius: 4px (softened polygon).

**Confidence glow:** The polygon has an inner glow layer. Opacity scales with `confidence`:
- HIGH → `rgba(191, 155, 48, 0.15)` glow
- MODERATE → `rgba(191, 155, 48, 0.08)` glow
- LOW → no glow
- NONE → polygon becomes dashed (`4px gap 4px`), fill removed

**Data points:** Small circles at each axis intersection. Size: 4px. Fill: `#bf9b30`. On hover: expands to 8px, shows metric overlay.

### 2.4 Temporal Behavior

The radar has **two polygon layers:**

1. **Current state** (solid, amber glow)
2. **Previous state** (dashed, `rgba(255,255,255,0.15)`, no fill)

When temporal data exists, the previous-state polygon is always visible as a ghost behind the current polygon. The delta between the two shapes is the visual representation of organizational change.

**Temporal drift animation:** When the temporal scope changes, both polygons smoothly morph from their previous values to the new values over 600ms using `cubic-bezier(0.16, 1, 0.3, 1)`.

**Axis emergence:** If a category appears that wasn't in the previous polygon, its axis point grows from the center outward (0→value over 400ms, spring physics).

### 2.5 Interaction

- **Hover on axis point:** Shows tooltip with axis name, current value, previous value, delta, and trend arrow.
- **Hover on polygon interior:** Shows the diagnostic state and confidence in the center of the polygon.
- **Click on axis point:** Expands a detail card below the radar showing the full evidence chain for that dimension.
- **Scope change:** Both polygons animate to new temporal window values.

### 2.6 Diagnostic State Overlay

The center of the radar shows the current diagnostic state:

| State | Center Text | Center Icon | Ambient Color |
|-------|------------|-------------|---------------|
| stable_low_friction | STABLE | ◎ | `rgba(34, 197, 94, 0.06)` — muted green |
| stable_elevated_friction | ELEVATED | ◉ | `rgba(191, 155, 48, 0.08)` — amber |
| emerging_pain | EMERGING | △ | `rgba(191, 155, 48, 0.12)` — stronger amber |
| accelerating_pain | ACCELERATING | ▲ | `rgba(239, 68, 68, 0.10)` — muted red |
| declining_pain | DECLINING | ▽ | `rgba(34, 197, 94, 0.10)` — green |
| volatile_friction | VOLATILE | ◇ | `rgba(249, 115, 22, 0.10)` — orange |
| insufficient_temporal_data | ACQUIRING | … | `rgba(255,255,255,0.04)` — dim |

The ambient color is a slow radial pulse (4s cycle) centered on the radar polygon.

### 2.7 Responsive States

| Viewport | Behavior |
|----------|----------|
| ≥1440px | Full radar (400px) with labels and detail cards |
| 1024–1439px | Radar (320px), labels abbreviated to 2-letter codes |
| 768–1023px | Radar (280px), axis labels hidden, tap to reveal |
| <768px | Compact radar (240px), detail cards in a bottom sheet |

---

## 3. Temporal Intelligence Timeline

### 3.1 Concept

The timeline is an **orbital track** — a horizontal time axis with signal events placed as luminous nodes. It tells the story of a company's friction journey.

The timeline is not a Gantt chart. It is an **investigation trail** — each node is evidence, each connection is causation, and the overall trajectory reveals the narrative.

### 3.2 Structure

```
                                                                              NOW
  ◆──────◆────◆◆◆──────◆────────◆────◆──────◆──────◆◆◆◆──◆────◆──────◆──◇
  │      │    |||      │        │    │      │      ||||  │    │      │   │
  L7     L14  L18-20   L25      L32  L38    L45    L50-53 L57  L62    L68  L30
  │      │    │        │        │    │      │      │     │    │      │   │
  ▼      ▼    ▼        ▼        ▼    ▼      ▼      ▼     ▼    ▼      ▼   ▼
  hire   lay  hiring   funding  ...  hire   tool   hire  lay  eng    CX  current
  CSM    off  spike    round         eng    ing    eng   off  blog   fric score
```

**Track line:** A horizontal axis spanning the lookback window. Color: `rgba(255,255,255,0.06)`. The track has subtle tick marks at regular intervals.

**Time labels:** Below the track. Font: `text-[10px] font-mono text-gray-600`. Show at appropriate intervals (daily for 7d, weekly for 30d, monthly for 90d, quarterly for 180d).

**NOW marker:** A bright vertical line at the rightmost edge. Color: `rgba(191, 155, 48, 0.4)`. Label: "NOW" in `text-[9px] font-semibold tracking-widest uppercase text-amber-400`.

**Signal nodes:** Circular markers on the track. Size varies by signal importance:
- Scored signals: 6px filled circle
- Discovery signals: 4px ring (unfilled)
- Category-specific signals: colored by category

**Category colors:**

| Category | Color | Hex |
|----------|-------|-----|
| reporting_fragmentation | Cool blue | `#60a5fa` |
| process_inefficiency | Warm amber | `#bf9b30` |
| tooling_inconsistency | Violet | `#a78bfa` |
| scaling_strain | Teal | `#2dd4bf` |
| customer_experience_friction | Red | `#f87171` |

**Cluster indicators:** When multiple signals fall within the same time window (7d/weekly bucket), they collapse into a **cluster node** — a larger circle with a count badge. Expanding a cluster reveals individual nodes with a spring animation.

**Event markers:** Significant events (layoffs, funding, acquisition) shown as diamond-shaped markers with amber glow, positioned above the track. Connected to signal clusters with thin amber lines.

### 3.3 Temporal Zones

The timeline is divided into **zones** based on the diagnostic state during each period:

| Zone | Background | Description |
|------|-----------|-------------|
| Stable low | `rgba(34, 197, 94, 0.03)` | Low friction, not changing |
| Stable elevated | `rgba(191, 155, 48, 0.03)` | Elevated friction, but stable |
| Emerging | `rgba(191, 155, 48, 0.06)` | Friction beginning to increase |
| Accelerating | `rgba(239, 68, 68, 0.06)` | Friction increasing rapidly |
| Declining | `rgba(34, 197, 94, 0.06)` | Friction decreasing |
| Volatile | `rgba(249, 115, 22, 0.04)` | Unpredictable changes |
| Insufficient | `rgba(255,255,255,0.02)` | Not enough data |

Zones are shown as horizontal bands across the timeline. They transition smoothly (400ms crossfade) when the temporal scope changes.

### 3.4 Score Overlay

A **score delta line** overlaid on the timeline. This is a thin SVG path showing the total friction score over time. Color: `rgba(191, 155, 48, 0.4)`. When the score is increasing (friction worsening), the line turns toward red. When decreasing, toward green.

Score snapshot points are shown as small diamonds on the line. On hover, show: timestamp, total score, delta from previous, dominant category.

### 3.5 Zoom and Scrub

**Scroll:** Vertical scroll zooms the timeline in/out (7d ↔ 30d ↔ 90d ↔ 180d). The current scope is highlighted in the header temporal nav.

**Drag:** Horizontal drag scrubs through time within the current scope.

**Click on node:** Opens an evidence detail card showing: signal type, signal text, source, confidence, related signals in the same cluster.

### 3.6 Temporal Drift Indicators

Between temporal zones, **drift arrows** show the direction of change:

- ↑ (friction increasing): `text-red-400/60`
- ↓ (friction decreasing): `text-emerald-400/60`
- → (stable): `text-gray-500/40`
- ↕ (volatile): `text-orange-400/60`

Drift arrows animate with a slow 3s pulse to draw attention to the transition.

### 3.7 Evidence Popups

On hover/tap of any signal node, an **evidence card** appears:

```
┌─────────────────────────────────────────┐
│ ◆ Process Inefficiency           HIGH   │
│─────────────────────────────────────────│
│ "3 senior ops managers hired in 2      │
│  weeks, no corresponding PM or         │
│  engineering hires"                     │
│                                         │
│ Source: LinkedIn Jobs                   │
│ Confidence: 0.87                        │
│ Category: process_inefficiency          │
│ Related: 4 signals in this cluster      │
│                                         │
│ △ Emerging · +0.42 delta (30d)         │
└─────────────────────────────────────────┘
```

Evidence cards appear with a 200ms spring animation from the node position. They dismiss on click-away or on node click elsewhere.

---

## 4. Signal Constellation View

### 4.1 Concept

The constellation view places the company at the center, with signals as luminous points orbiting in category-weighted clusters. The closer a signal cluster is to the center, the higher its friction contribution.

This is an **SVG-based force-directed layout** — not a full physics simulation. Positions are deterministic based on category, confidence, and temporal weight.

### 4.2 Layout

```
                    ◆ reporting
                   ╱
         ◆ ◆ ◆ ◆╱
        ◆◆◆◆───◎────────── ◆ process
        ◆◆◆◆   ╲              ◆ ◆ ◆
    tooling◆◆   ╲
      ◆◆◆◆◆     ◆ CX
       ◆◆◆◆       ◆◆◆
                   ◆◆
```

**Center node:** Company name + dominant friction. Size: 48px. Glow: amber based on confidence.

**Signal nodes:** Each scored signal is a circle. Size: 6px for standard, 10px for high-confidence. Color: category color. Opacity: `0.4` (low confidence) → `1.0` (high confidence).

**Orbital rings:** Category groups are arranged around the center at distances proportional to their contribution to total friction. Higher friction categories orbit closer.

**Connection lines:** Thin lines from each signal to the center. Color: category color at 0.15 opacity. On hover, the line brightens to 0.6 opacity and the connected signal glows.

**Cluster labels:** Category names positioned outside each cluster ring. Font: `text-[10px] font-medium tracking-widest uppercase text-gray-500`.

### 4.3 Temporal Playback Mode

A **play button** in the constellation toolbar activates temporal playback:

1. Signal nodes appear/disappear based on their `captured_at` timestamp.
2. Nodes that arrive during the playback window animate in with a pulse (expand from 0→size over 300ms, spring).
3. Nodes that depart fade out (opacity 1→0 over 200ms).
4. The company center glow intensity changes based on the temporal diagnostic state at each point in time.
5. A scrubber at the bottom shows current position in the temporal window.

Playback speed: 1 day per second (configurable).

### 4.4 Interaction

- **Hover on node:** Highlights the node, dims all others to 0.2 opacity, shows evidence card.
- **Click on node:** Opens full signal detail in a side panel.
- **Hover on cluster label:** Highlights all nodes in that category, dims others.
- **Click on center node:** Navigates to Company Command Center.

### 4.5 Rendering Strategy

**SVG for nodes and lines** (up to 200 signals): SVG handles this well and supports CSS animations and hover states.

**Canvas for 200+ signals:** Switch to Canvas rendering when signal count exceeds 200. Use `requestAnimationFrame` for smooth animation. Hit detection via spatial index (quadtree).

**No WebGL needed.** The constellation is 2D. Reserve WebGL only if 3D perspective is added later (not recommended for this view).

---

## 5. Company Command Center

### 5.1 Layout

The command center is the primary company intelligence screen. It uses a **modular card grid** with clear hierarchy.

```
┌────────────────────────────────────────────────────────────────────┐
│ FRICTIONRADAR                                    [30D] [90D] [180D]│
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌─────────────────┐  ┌──────────────────────────────────────────┐│
│  │                  │  │                                          ││
│  │    RADAR         │  │         STRATEGIC INTERPRETATION         ││
│  │    (polygon)     │  │                                          ││
│  │                  │  │  What we know · What we don't know      ││
│  │    ST: EMERGING  │  │  Next best step · Attack angle           ││
│  │    CF: MODERATE  │  │                                          ││
│  │                  │  │                                          ││
│  └─────────────────┘  └──────────────────────────────────────────┘│
│                                                                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────┐│
│  │ TEMPORAL   │ │ DELTA      │ │ VELOCITY   │ │ EVIDENCE       ││
│  │ STATUS     │ │ SUMMARY    │ │ METRICS    │ │ CHAIN          ││
│  │            │ │            │ │            │ │                ││
│  │ △ EMERGING │ │ +0.42 Δ   │ │ 2.3 sig/wk │ │ 23 signals     ││
│  │ MODERATE   │ │ DECLINING  │ │ ACCEL      │ │ 4 categories   ││
│  └────────────┘ └────────────┘ └────────────┘ └────────────────┘│
│                                                                    │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐│
│  │ TIMELINE                 │  │ ELIGIBILITY & POSITIONING         ││
│  │                          │  │                                  ││
│  │ ◆──◆◆──◆──────◆──◆◆◆──◇│  │  CONDITIONAL · early_positioning ││
│  │                          │  │  Gate: pain_emerging ✓            ││
│  └──────────────────────────┘  │  Confidence: moderate            ││
│                                └──────────────────────────────────┘│
│                                                                    │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐│
│  │ SIGNALS BY CATEGORY      │  │ ATS INTELLIGENCE                 ││
│  │                          │  │                                  ││
│  │ (bar chart or list)      │  │ (job roles, functional areas)    ││
│  └──────────────────────────┘  └──────────────────────────────────┘│
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│ 48 signals · 3 snapshots · confidence: moderate · scope: 30D      │
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 Section Specifications

#### Company Overview + Radar (top-left, 40% width)

The radar from Section 2. Below it: company name (18px, `text-white font-semibold`), domain (`text-gray-500 text-sm`), temporal state badge, confidence badge.

#### Strategic Interpretation (top-right, 60% width)

The most important section. Structured as:

1. **What we know** — Primary evidence summary. `text-gray-200 text-sm leading-relaxed`.
2. **What we don't know yet** — Knowledge gaps. `text-gray-500 text-sm italic`.
3. **Main pain** — Red-accented. `text-red-400 text-sm font-medium`.
4. **Where pain lives** — `text-gray-300 text-sm`.
5. **What the company needs** — Green-accented card. `bg-emerald-950/30 border border-emerald-800/30`.
6. **Best attack angle** — Blue-accented card. `bg-blue-950/30 border border-blue-800/30`.
7. **Next best step** — Amber-accented card. `bg-amber-950/30 border border-amber-800/30`.

Each section has a small label in `text-[10px] font-semibold tracking-widest uppercase`.

#### Metric Cards (row 2, equal width)

Four cards in a grid. Each card:

```
┌────────────────────┐
│ TEMPORAL STATUS    │  ← label: text-[10px] tracking-widest uppercase text-gray-500
│                    │
│ △ EMERGING PAIN   │  ← value: text-2xl font-semibold text-amber-400
│ MODERATE CONFIDENCE│  ← subtitle: text-xs text-gray-500
│                    │
│ 3 snapshots · 12  │  ← detail: text-[10px] text-gray-600 font-mono
│ scored signals     │
└────────────────────┘
```

Background: `bg-[#0b0f12] border border-gray-800/50`. Border glow on hover: `border-amber-900/30`.

#### Timeline (row 3, 60% width)

The timeline from Section 3. Compact mode by default (signal nodes only, no evidence text). Click to expand.

#### Eligibility & Positioning (row 3, 40% width)

Shows:
- Eligibility status with gate visualization
- Temporal override status (if applicable)
- Confidence band
- Positioning readiness assessment

#### Signals by Category (row 4, 50% width)

Horizontal bar chart showing category distribution. Bars are category-colored. Animated entrance.

#### ATS Intelligence (row 4, 50% width)

Top functional areas, hiring velocity, role distribution.

### 5.3 Card System

All cards share a common anatomy:

```
┌──────────────────────────────┐
│ LABEL            ·  ·  ·  ·  │  ← header row
│                              │
│ [CONTENT]                    │  ← body
│                              │
└──────────────────────────────┘
```

- Background: `bg-[#0b0f12]`
- Border: `border border-gray-800/50`
- Border radius: `rounded-lg` (8px)
- Header label: `text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500`
- Padding: `p-5`
- Gap between cards: `gap-4`
- Signal lock animation on data load: amber pulse on border (200ms)

---

## 6. Temporal Diagnostic States

Each diagnostic state has a **unique motion language, visual intensity, atmospheric behavior, and UI tone.**

### 6.1 stable_low_friction

**Motion:** Slow, steady pulse. The radar polygon gently breathes (scale 1.0 → 1.01, 4s cycle).

**Visual intensity:** Low. Muted green accents. No glow.

**Atmosphere:** `rgba(34, 197, 94, 0.03)` radial gradient, 8s cycle drift.

**UI tone:** Calm. Sections use `text-emerald-400` for labels. No urgency indicators. "All clear" iconography.

**Signal behavior:** Signal nodes are steady, no pulse. Timeline zones are light green bands.

**Card style:** Standard dark card. Status badge: `bg-emerald-950/40 text-emerald-400 border-emerald-800/30`.

### 6.2 stable_elevated_friction

**Motion:** Steady with subtle tension. Radar polygon is slightly larger, with a slow amber pulse (scale 1.0 → 1.02, 3.5s cycle).

**Visual intensity:** Medium-low. Warm amber accents. Soft inner glow on radar.

**Atmosphere:** `rgba(191, 155, 48, 0.04)` radial gradient, 6s cycle.

**UI tone:** Attentive. Sections use `text-amber-400` for labels. "Elevated but stable" messaging.

**Signal behavior:** Signal nodes pulse gently every 4s. Timeline zones are light amber bands.

**Card style:** Standard dark card with subtle amber border on hover. Status badge: `bg-amber-950/40 text-amber-400 border-amber-800/30`.

### 6.3 emerging_pain

**Motion:** Emerging. The radar polygon has a growth animation — it slowly expands outward from the previous shape over 2s, then holds. Repeats every 30s.

**Visual intensity:** Medium. Amber accents with occasional brighter pulses. Inner glow strengthens when new signals arrive.

**Atmosphere:** `rgba(191, 155, 48, 0.06)` radial gradient, 5s cycle. Scan line appears every 60s.

**UI tone:** Investigative. "Friction is beginning to emerge" language. `text-amber-300` for key values. Action labels in amber.

**Signal behavior:** New signal nodes appear with a pulse animation (0→size, 300ms spring). Existing nodes pulse every 3s. Timeline zone shows growing amber band.

**Card style:** Amber-accented cards. Status badge: `bg-amber-950/50 text-amber-300 border-amber-700/40` with a subtle pulse animation (opacity 0.7→1.0, 3s cycle).

### 6.4 accelerating_pain

**Motion:** Accelerating. The radar polygon expands outward more aggressively (scale 1.0→1.04, 2s), then partially contracts (1.04→1.02), then expands again. This creates a "heartbeat" pattern with increasing intensity.

**Visual intensity:** High. Red-amber accents. Strong inner glow. Scan lines appear every 30s.

**Atmosphere:** `rgba(239, 68, 68, 0.05)` radial gradient, 4s cycle. The gradient pulses.

**UI tone:** Urgent. "Friction is accelerating" language. `text-red-400` for key values. Red-accented action cards. "Position now" emphasis.

**Signal behavior:** New signal nodes appear with a sharp pulse (0→1.5x→size, 400ms). All nodes pulse every 2s. Clusters compress closer to center. Timeline zone shows expanding red band.

**Card style:** Red-accented cards. Status badge: `bg-red-950/50 text-red-300 border-red-700/40` with pulse animation (opacity 0.6→1.0, 2s cycle). Card borders have a subtle red glow on hover.

### 6.5 declining_pain

**Motion:** Easing. The radar polygon slowly contracts toward center over 3s, then holds. Subtle relief animation.

**Visual intensity:** Low-medium. Green accents. Soft green glow.

**Atmosphere:** `rgba(34, 197, 94, 0.05)` radial gradient, 7s cycle.

**UI tone:** Positive. "Friction is declining" language. `text-emerald-400` for key values. Green-accented cards.

**Signal behavior:** Signal nodes fade slightly (opacity decreases by 0.1). Timeline zone shows narrowing green band.

**Card style:** Green-accented cards. Status badge: `bg-emerald-950/40 text-emerald-400 border-emerald-700/30`.

### 6.6 volatile_friction

**Motion:** Unpredictable. The radar polygon shape-shifts every 2-3s between two slightly different configurations. Not smooth — it snaps between states.

**Visual intensity:** Medium. Orange accents. Flickering glow.

**Atmosphere:** `rgba(249, 115, 22, 0.04)` radial gradient, rapid 3s cycle.

**UI tone:** Cautious. "Friction direction is volatile" language. `text-orange-400` for key values. Warning cards. "Monitor closely" emphasis.

**Signal behavior:** Signal nodes randomly change opacity (0.5→1.0→0.6). Clusters shift position slightly. Timeline shows alternating orange bands.

**Card style:** Orange-accented cards. Status badge: `bg-orange-950/40 text-orange-400 border-orange-700/30` with a flicker animation (opacity 0.7→1.0→0.8, 1.5s cycle).

### 6.7 insufficient_temporal_data

**Motion:** Minimal. The radar polygon is dashed, unfilled. A slow scanning animation sweeps across the polygon shape (like a radar sweep line).

**Visual intensity:** Lowest. Gray only. No glow.

**Atmosphere:** `rgba(255,255,255,0.02)` — barely perceptible.

**UI tone:** Patient. "Acquiring signals" language. `text-gray-500` for values. No action cards. "More data needed" emphasis.

**Signal behavior:** Very few visible signal nodes. Existing nodes are dim (opacity 0.3). Occasional scan pulse every 10s.

**Card style:** Standard dark card, no accent color. Status badge: `bg-gray-900 text-gray-500 border-gray-700/30`.

---

## 7. Live Signal Motion System

### 7.1 Signal Propagation

When a new signal arrives (via data refresh), the animation sequence is:

1. **Origin pulse:** A small amber circle (8px) appears at the signal's position on the constellation/timeline. Expands to 24px over 300ms, then fades. This is the "signal arrived" indicator.

2. **Node formation:** The signal node grows from 0px to its final size (6-10px) over 200ms using `spring(1, 80, 10)`.

3. **Connection draw:** The line from the signal to the center node draws from the node toward the center over 400ms. Stroke-dashoffset animation.

4. **Center pulse:** The company center node pulses once (scale 1.0→1.05→1.0, 300ms) in the category color.

5. **Metric update:** Any affected metric cards update their values with a 200ms number transition (old value fades up, new value fades in).

### 7.2 Pulse Waves

Pulse waves are **concentric rings** that expand outward from a node:

- **Radius:** 0 → 40px over 600ms
- **Opacity:** 0.4 → 0 over 600ms
- **Color:** Category color (or amber for generic)
- **Trigger:** New signal arrival, temporal state change, manual refresh

Only one pulse wave can be active per node at a time. If a new trigger arrives during an active pulse, the current pulse completes before the new one starts.

### 7.3 Evidence Emergence

When an evidence card appears:

1. Card scales from 0.95→1.0 and fades in from opacity 0→1 over 200ms.
2. A thin amber border line draws from the triggering node to the card (300ms).
3. The card has a subtle glow on its border: `box-shadow: 0 0 20px rgba(191, 155, 48, 0.1)`.
4. On dismiss: card fades to 0 opacity and scales to 0.98 over 150ms.

### 7.4 Friction Escalation Visuals

When temporal state transitions from one state to another (e.g., STABLE → EMERGING):

1. The **previous state's** atmospheric layer fades out over 600ms.
2. The **new state's** atmospheric layer fades in over 600ms (crossfaded).
3. The **radar polygon** morphs to the new shape over 800ms (`cubic-bezier(0.16, 1, 0.3, 1)`).
4. The **status badge** text transitions: old text fades up (opacity 1→0, 150ms), new text fades in (opacity 0→1, 200ms).
5. A **transition alert** slides in from the right: "State changed: STABLE → EMERGING PAIN" with the appropriate color. Dismisses after 5s or on click.

### 7.5 Scanning Sweeps

The **scan sweep** is a thin amber line that sweeps across the radar polygon:

- **Angle:** 0° → 360° over 4s
- **Width:** 2px
- **Color:** `rgba(191, 155, 48, 0.3)` with a 20px gradient trail
- **Trigger:** Data refresh, manual analysis trigger, temporal scope change
- **Frequency:** Max once per 30s (debounced)

The sweep uses CSS conic-gradient animation or SVG rotation transform.

### 7.6 Drift Movement

On the timeline, temporal drift is shown as:

- A subtle horizontal movement of zone boundaries (2px drift over 8s).
- The "NOW" marker slowly brightens and dims (opacity 0.4→0.6, 5s cycle).
- Score delta line slightly oscillates in y-axis (±2px, 10s cycle) when volatile.

---

## 8. Technical Implementation

### 8.1 Component Architecture

```
src/
├── app/
│   ├── App.tsx                          # Shell with providers
│   ├── routes.tsx                       # Route definitions
│   └── providers.tsx                    # Theme, query, motion providers
├── components/
│   ├── shell/
│   │   ├── AppShell.tsx                 # Main layout (header, nav, content, status)
│   │   ├── Header.tsx                   # Top bar with search, scope, user
│   │   ├── NavRail.tsx                  # Left navigation rail
│   │   ├── StatusBar.tsx                # Bottom status bar
│   │   ├── CommandPalette.tsx           # Cmd+K company search
│   │   └── TemporalScopeSelector.tsx    # 7D/30D/90D/180D scope control
│   ├── radar/
│   │   ├── RadarCanvas.tsx              # SVG radar polygon chart
│   │   ├── RadarAxis.tsx                # Single axis line + label
│   │   ├── RadarPolygon.tsx             # Current + previous polygons
│   │   ├── RadarPoint.tsx               # Interactive data point
│   │   ├── RadarStateOverlay.tsx        # Center diagnostic state display
│   │   └── RadarDetail.tsx              # Expanded axis detail card
│   ├── timeline/
│   │   ├── TemporalTimeline.tsx         # Main timeline container
│   │   ├── TimelineTrack.tsx            # Horizontal time axis
│   │   ├── TimelineNode.tsx             # Signal node on track
│   │   ├── TimelineCluster.tsx          # Clustered nodes with count badge
│   │   ├── TimelineZone.tsx             # Colored zone band
│   │   ├── TimelineScoreLine.tsx        # SVG score overlay path
│   │   ├── TimelineEventMarker.tsx       # Diamond event markers
│   │   └── TimelineEvidencePopup.tsx    # Hover evidence card
│   ├── constellation/
│   │   ├── SignalConstellation.tsx      # Main constellation container
│   │   ├── ConstellationNode.tsx        # Individual signal node
│   │   ├── ConstellationCenter.tsx      # Company center node
│   │   ├── ConstellationLine.tsx        # Connection line
│   │   ├── ConstellationCluster.tsx     # Category cluster group
│   │   └── ConstellationPlayback.tsx    # Temporal playback controls
│   ├── command/
│   │   ├── CommandCenter.tsx            # Main company intelligence page
│   │   ├── CompanyOverview.tsx          # Name, domain, meta
│   │   ├── StrategicInterpretation.tsx  # What we know / don't know / next step
│   │   ├── MetricCard.tsx              # Reusable metric card
│   │   ├── EligibilityPanel.tsx        # Positioning eligibility + gates
│   │   └── CategoryBreakdown.tsx        # Signal distribution by category
│   ├── temporal/
│   │   ├── TemporalStatusCard.tsx       # (existing, redesigned for dark theme)
│   │   ├── TrendByCategoryChart.tsx     # (existing, redesigned)
│   │   ├── ScoreDeltaSummary.tsx        # (existing, redesigned)
│   │   ├── SignalVelocityChart.tsx      # (existing, redesigned)
│   │   ├── EmergingPainPanel.tsx        # (existing, redesigned)
│   │   ├── DecliningPainPanel.tsx       # (existing, redesigned)
│   │   ├── EvidenceTimeline.tsx         # (existing, redesigned)
│   │   ├── InsufficientTemporalData.tsx  # (existing, redesigned)
│   │   └── StrategicInterpretation.tsx  # (existing, redesigned)
│   ├── motion/
│   │   ├── Atmosphere.tsx               # Background radial gradient + drift
│   │   ├── GridOverlay.tsx              # Subtle dot grid
│   │   ├── ScanLine.tsx                 # Amber horizontal scan line
│   │   ├── SignalPulse.tsx              # Expanding ring animation
│   │   ├── StateTransition.tsx           # Diagnostic state change transition
│   │   └── SectionReveal.tsx             # Staggered section entrance animation
│   └── common/
│       ├── SectionCard.tsx              # Redesigned dark theme card
│       ├── Badge.tsx                    # Redesigned dark theme badge
│       ├── EmptyState.tsx               # Redesigned empty state
│       ├── LoadingState.tsx             # Scan-sequence loading
│       └── ErrorState.tsx               # Redesigned error state
├── hooks/
│   ├── useTemporalData.ts               # (existing)
│   ├── useCompanyDetail.ts              # (existing)
│   ├── useTheme.ts                      # Dark theme context
│   └── useMotionConfig.ts              # Reduced motion detection
├── services/
│   ├── temporal.ts                      # (existing)
│   ├── apiClient.ts                     # (existing, update base URL)
│   └── ...
├── types/
│   ├── temporal.ts                      # (existing)
│   └── ...
└── styles/
    ├── globals.css                       # Dark theme base styles
    └── motion.css                       # Keyframe animations
```

### 8.2 Route Structure

```
/                           → Redirect to /directory
/directory                  → CompanyDirectory (list view)
/company/:id                → CommandCenter (primary intelligence screen)
/company/:id/radar          → RadarView (full-screen radar)
/company/:id/timeline       → TimelineView (full-screen timeline)
/company/:id/constellation  → ConstellationView (full-screen constellation)
/company/:id/intelligence   → IntelligenceView (analysis + interpretation)
/settings                   → Settings (scope defaults, preferences)
```

Navigation between views uses the `view morph` transition (400ms, `cubic-bezier(0.16, 1, 0.3, 1)`).

### 8.3 Motion System Architecture

**Framer Motion** is the primary motion library. All animations use `motion` components or `useAnimation`.

**Motion config layer:**

```typescript
// hooks/useMotionConfig.ts
export function useMotionConfig() {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  return {
    enabled: !prefersReducedMotion,
    duration: {
      fast: prefersReducedMotion ? 0 : 150,     // hovers, badges
      normal: prefersReducedMotion ? 0 : 300,    // sections, cards
      slow: prefersReducedMotion ? 0 : 600,      // page transitions
      morph: prefersReducedMotion ? 0 : 800,     // radar reshape
    },
    easing: {
      entrance: [0.16, 1, 0.3, 1],   // expo-out
      exit: [0.7, 0, 0.84, 0],       // expo-in
      spring: { stiffness: 100, damping: 12 },
    },
  };
}
```

**Reduced motion:** When `prefers-reduced-motion: reduce` is active, all animation durations become 0. Content appears instantly. Only color changes persist (no motion).

**Motion categories:**

| Category | Duration | Trigger | Example |
|----------|----------|---------|---------|
| Micro | 0-150ms | Hover, focus | Badge glow, tooltip appear |
| Standard | 150-300ms | Data load, toggle | Section reveal, card appear |
| Transition | 300-600ms | Navigation, scope change | View morph, timeline scrub |
| Cinematic | 600-1200ms | State change, new data | Radar reshape, signal propagation |

**Maximum concurrent animations:** 3. If more than 3 elements need animation, the lowest-priority ones are delayed (staggered by 100ms).

### 8.4 Visualization Recommendations

| Visualization | Library | Rationale |
|---------------|---------|-----------|
| Radar polygon | D3.js (custom SVG) | Full control over polygon geometry, animation, and interaction. Recharts/Visx don't support custom polygon morphing. |
| Timeline track | DOM + Framer Motion | Simple horizontal layout. No chart library needed. |
| Score line overlay | D3.js (line generator) | Smooth curves with temporal interpolation. |
| Category bar chart | Recharts | Simple bar chart, well-supported. |
| Signal constellation | DOM + Framer Motion (≤200 signals) / Canvas (>200) | Force-directed layout is deterministic, not physics-based. DOM is fine for ≤200 with hover states. Canvas for performance beyond that. |
| Metric cards | DOM + Framer Motion | Pure layout, no chart library. |

**No three.js.** The radar and constellation are 2D. Three.js adds complexity without benefit for this use case.

### 8.5 Performance Strategy

1. **Data fetching:** All temporal data uses React Query with `staleTime: 5 * 60 * 1000` (5 minutes). Refetch on window focus for live data feel.

2. **Radar rendering:** Use `useMemo` for polygon points calculation. Only recalculate when temporal data or scope changes. D3 renders to SVG — no re-renders on hover.

3. **Timeline virtualization:** Only render nodes visible in the viewport. Use `IntersectionObserver` to lazy-load off-screen sections.

4. **Constellation:** Switch from DOM to Canvas when signal count exceeds 200. Use `OffscreenCanvas` in a Web Worker for constellation layout calculation if needed.

5. **Animation throttling:** Use `requestAnimationFrame` for all custom animations. Debounce resize handlers to 16ms (one frame).

6. **Bundle splitting:** Radar, timeline, and constellation are lazy-loaded:
   ```typescript
   const RadarView = lazy(() => import('../radar/RadarCanvas'));
   const TemporalTimeline = lazy(() => import('../timeline/TemporalTimeline'));
   const SignalConstellation = lazy(() => import('../constellation/SignalConstellation'));
   ```

7. **CSS containment:** All card components use `contain: layout style paint` to prevent layout thrashing.

### 8.6 Responsive Behavior

| Viewport | Layout | Radar | Timeline | Constellation |
|----------|--------|-------|----------|---------------|
| ≥1440px | Full grid, 2-column | 400px, full labels | Full timeline with zones | Full force-directed |
| 1024–1439px | Full grid, narrower | 320px, abbreviated labels | Compact timeline, no zones | Compact, fewer labels |
| 768–1023px | Single column, stacked | 280px, labels on tap | Horizontal scroll timeline | Simplified, tap for detail |
| <768px | Single column, full width | 240px, compact | Horizontal scroll, minimal | List view fallback |

### 8.7 Dark Mode Rendering

The entire interface is dark-first. No light mode toggle.

**Text contrast:** All text meets WCAG AAA on dark backgrounds:
- Primary text: `text-gray-100` on `#050505` (contrast ratio 17.5:1)
- Secondary text: `text-gray-400` on `#050505` (contrast ratio 5.7:1)
- Label text: `text-gray-500` on `#0b0f12` (contrast ratio 4.8:1)

**Amber accents:** `#bf9b30` on `#050505` has contrast ratio 6.2:1 (passes AA).

**Card borders:** `border-gray-800/50` — visible but not distracting. On hover, borders transition to `border-gray-700/70` over 200ms.

**Focus states:** All interactive elements use `ring-2 ring-amber-500/50 ring-offset-2 ring-offset-[#050505]` for keyboard accessibility.

### 8.8 Avoiding Motion Overload

**Rules:**

1. **Never more than 3 concurrent animations.** Stagger entrance animations by 100ms.
2. **No animation longer than 1200ms.** Even cinematic transitions settle within 1.2s.
3. **No animation loops longer than 10s.** Ambient effects (radar breathing, gradient drift) have long cycles to avoid fatigue.
4. **No bounce effects.** Use spring easing with moderate damping (12-15). Never use `spring(1, 300, 10)` or similar bouncy presets.
5. **No particle effects.** Signal nodes are dots, not particles.
6. **No parallax scrolling.** It adds motion without signal value.
7. **No decorative animation.** Every animation must encode information (state, value, arrival, departure).
8. **Reduced motion kills everything.** When `prefers-reduced-motion: reduce` is active, all durations become 0.

---

## 9. Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal:** Shell, theme, and basic components.

- [ ] Dark theme system (`globals.css`, Tailwind config)
- [ ] AppShell layout (header, nav rail, content, status bar)
- [ ] SectionCard (dark theme)
- [ ] Badge (dark theme with state colors)
- [ ] LoadingState (scan sequence)
- [ ] MetricCard
- [ ] TemporalScopeSelector
- [ ] Motion config (`useMotionConfig`)
- [ ] Atmosphere layer (background gradient)
- [ ] Grid overlay
- [ ] Route structure

**Deliverable:** Navigable shell with dark theme. No data. Card placeholders with scan-loading animation.

### Phase 2: Command Center (Week 2-3)

**Goal:** Full company intelligence screen with existing temporal components, redesigned for dark theme.

- [ ] CommandCenter page layout
- [ ] CompanyOverview header
- [ ] StrategicInterpretation (dark theme redesign)
- [ ] TemporalStatusCard (dark theme redesign)
- [ ] TrendByCategoryChart (dark theme redesign)
- [ ] ScoreDeltaSummary (dark theme redesign)
- [ ] SignalVelocityChart (dark theme redesign)
- [ ] EmergingPainPanel (dark theme redesign)
- [ ] DecliningPainPanel (dark theme redesign)
- [ ] EvidenceTimeline (dark theme redesign)
- [ ] InsufficientTemporalData (dark theme redesign)
- [ ] EligibilityPanel
- [ ] CategoryBreakdown (bar chart)
- [ ] Section reveal animations
- [ ] State transition animations

**Deliverable:** Fully functional company command center with real API data, dark theme, and state-appropriate animations.

### Phase 3: Radar (Week 3-4)

**Goal:** Organizational radar visualization.

- [ ] D3 radar polygon component
- [ ] RadarAxis with labels and data points
- [ ] RadarPolygon with current/previous layers
- [ ] Confidence glow layer
- [ ] RadarStateOverlay (center diagnostic state)
- [ ] RadarDetail (hover expanded axis)
- [ ] Polygon morph animation on scope change
- [ ] Ambient pulse per diagnostic state
- [ ] Radar full-screen view

**Deliverable:** Interactive radar polygon with temporal behavior, state-dependent atmosphere, and hover details.

### Phase 4: Timeline (Week 4-5)

**Goal:** Temporal intelligence timeline.

- [ ] TimelineTrack (horizontal time axis)
- [ ] TimelineNode (signal nodes, category-colored)
- [ ] TimelineCluster (collapsed groups)
- [ ] TimelineZone (diagnostic state bands)
- [ ] TimelineScoreLine (D3 score overlay)
- [ ] TimelineEventMarker (diamond markers)
- [ ] TimelineEvidencePopup (hover cards)
- [ ] Scope scrub animation
- [ ] Cluster expand/collapse
- [ ] Timeline full-screen view

**Deliverable:** Interactive timeline with zones, signal nodes, score line, and evidence popups.

### Phase 5: Constellation (Week 5-6)

**Goal:** Signal constellation view.

- [ ] ConstellationNode (category-colored signal nodes)
- [ ] ConstellationCenter (company node)
- [ ] ConstellationLine (connection lines)
- [ ] ConstellationCluster (category grouping)
- [ ] ConstellationPlayback (temporal playback mode)
- [ ] Canvas fallback for >200 signals
- [ ] Signal pulse animation
- [ ] Constellation full-screen view

**Deliverable:** Interactive constellation with category clusters, temporal playback, and evidence popups.

### Phase 6: Polish & Integration (Week 6-7)

**Goal:** Transitions, edge cases, performance.

- [ ] View morph transitions (radar ↔ company ↔ timeline ↔ constellation)
- [ ] Command palette (Cmd+K)
- [ ] Company switch crossfade
- [ ] Reduced motion support
- [ ] Performance audit (Lighthouse, bundle size)
- [ ] Responsive breakpoint testing
- [ ] Accessibility audit (keyboard navigation, screen reader)
- [ ] Error states (API failure, 404, empty data)
- [ ] Loading sequence polish
- [ ] Status bar live metrics
- [ ] E2E testing

**Deliverable:** Production-ready interface with all views, transitions, and edge cases handled.

---

## 10. Cinematic Microinteractions

### 10.1 Signal Lock

When data arrives for a section, the section card border briefly flashes amber:

```
Timeline: 0ms → border-amber-500/40 (200ms) → border-gray-800/50
```

This creates a "lock on" feeling — the system acquired the signal and is displaying it.

### 10.2 Confidence Pulse

The diagnostic state badge subtly pulses based on confidence:

- HIGH: Opacity 0.8→1.0, 4s cycle
- MODERATE: Opacity 0.7→1.0, 3s cycle
- LOW: Opacity 0.6→1.0, 2s cycle
- NONE: Static, no pulse

### 10.3 Metric Counter

When a metric value changes (e.g., signal count updates), the number uses a **counter animation:**

```typescript
<motion.span
  key={value}
  initial={{ opacity: 0, y: 8 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 200, ease: [0.16, 1, 0.3, 1] }}
>
  {value}
</motion.span>
```

The old number slides up and fades, the new number slides in from below.

### 10.4 Temporal Scope Scrub

When changing the temporal scope (7D → 30D → 90D):

1. All section cards simultaneously crossfade (200ms).
2. The radar polygon morphs to new shape (600ms).
3. The timeline compresses/expands (400ms).
4. A brief amber flash appears at the scope boundary (100ms).
5. Metric values counter-animate to new values (200ms each, staggered by 50ms).

### 10.5 Section Reveal

When a section enters the viewport:

```typescript
<motion.div
  initial={{ opacity: 0, y: 4 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 300, ease: [0.16, 1, 0.3, 1], delay: index * 0.05 }}
>
```

Each section is delayed by 50ms from the previous one, creating a cascade reveal.

### 10.6 Hover Glow

On card hover, a subtle amber glow appears at the card border:

```
Default: border-gray-800/50, box-shadow: none
Hover:   border-gray-700/70, box-shadow: 0 0 30px rgba(191, 155, 48, 0.04)
Transition: 200ms ease
```

### 10.7 Evidence Link Draw

When an evidence card appears for a signal node:

```typescript
// SVG path with stroke-dashoffset animation
<motion.line
  initial={{ pathLength: 0, opacity: 0 }}
  animate={{ pathLength: 1, opacity: 0.4 }}
  transition={{ duration: 300, ease: [0.16, 1, 0.3, 1] }}
/>
```

The line draws from the node to the card, creating a visual connection.

---

## 11. Temporal Intelligence Storytelling

The interface must tell a story, not display data. Here are three narrative patterns:

### 11.1 The Emergence Narrative

> "Three weeks ago, nothing. Two weeks ago, a flicker. Now, it's accelerating."

**Interface behavior:**

1. Timeline shows a quiet period (gray zone) on the left.
2. An amber signal cluster appears (first hiring spike, week 2).
3. The radar polygon slowly expands toward the emerging category axis.
4. The diagnostic state transitions from STABLE → EMERGING with a subtle amber pulse.
5. A transition alert slides in: "Emerging: Process friction detected."
6. The strategic interpretation card appears with: "What we know" → "Process inefficiency signals beginning 2 weeks ago. Hiring in operations outpacing PM and engineering support."
7. The eligibility panel shows: "CONDITIONAL · early_positioning" with the temporal gate passed.

### 11.2 The Acceleration Narrative

> "We saw this coming. Now it's confirmed and intensifying."

**Interface behavior:**

1. The radar polygon has been pulsing for a week (EMERGING state).
2. New signals arrive — the constellation gains 3 new nodes in rapid succession (spring animations).
3. The diagnostic state transitions: EMERGING → ACCELERATING.
4. The transition alert: "State change: EMERGING → ACCELERATING PAIN" with a red flash.
5. The metric cards update: delta changes from +0.32 to +0.81. Confidence upgrades from MODERATE to HIGH.
6. The radar polygon expands more aggressively (heartbeat animation).
7. Strategic interpretation updates: "Friction is accelerating in operations workflows. Consider immediate positioning."

### 11.3 The Stabilization Narrative

> "What was rising has plateaued. The friction is still there, but it's no longer getting worse."

**Interface behavior:**

1. The radar polygon has been in ACCELERATING state with its heartbeat animation.
2. Over the 30-day scope, the polygon begins to stabilize — the current and previous shapes converge.
3. The diagnostic state transitions: ACCELERATING → STABLE_ELEVATED.
4. The transition alert: "State change: ACCELERATING → STABLE ELEVATED" with a warm amber-to-amber transition.
5. The timeline shows the acceleration zone giving way to a stable zone.
6. Strategic interpretation: "Friction in operations has stabilized at an elevated level. This is not improving, but it's no longer worsening."
7. The eligibility panel: still eligible, but the positioning opportunity is different — "Position for sustained operations pain, not emergency intervention."

---

## 12. Design Tokens

### 12.1 Colors

```css
:root {
  /* Primary backgrounds */
  --bg-primary: #050505;
  --bg-secondary: #0b0f12;
  --bg-tertiary: #101418;
  --bg-card: #0b0f12;
  --bg-card-hover: #0f1419;

  /* Text */
  --text-primary: #f3f4f6;     /* gray-100 */
  --text-secondary: #9ca3af;   /* gray-400 */
  --text-tertiary: #6b7280;    /* gray-500 */
  --text-label: #6b7280;      /* gray-500, tracking-widest uppercase */
  --text-mono: #4b5563;        /* gray-600, for data values */

  /* Accent - Amber/Gold */
  --accent-primary: #bf9b30;
  --accent-glow: rgba(191, 155, 48, 0.15);
  --accent-dim: rgba(191, 155, 48, 0.08);
  --accent-border: rgba(191, 155, 48, 0.3);

  /* State colors */
  --state-stable: #22c55e;     /* green-500 */
  --state-elevated: #bf9b30;   /* amber */
  --state-emerging: #d4a030;   /* amber-gold */
  --state-accelerating: #ef4444; /* red-500 */
  --state-declining: #22c55e;  /* green-500 */
  --state-volatile: #f97316;   /* orange-500 */
  --state-insufficient: #6b7280; /* gray-500 */

  /* Category colors */
  --cat-reporting: #60a5fa;    /* blue-400 */
  --cat-process: #bf9b30;      /* amber */
  --cat-tooling: #a78bfa;     /* violet-400 */
  --cat-scaling: #2dd4bf;     /* teal-400 */
  --cat-cx: #f87171;          /* red-400 */

  /* Borders */
  --border-default: rgba(255,255,255,0.06);
  --border-card: rgba(255,255,255,0.08);
  --border-hover: rgba(255,255,255,0.12);
  --border-accent: rgba(191, 155, 48, 0.3);

  /* Shadows */
  --shadow-card: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-elevated: 0 4px 12px rgba(0,0,0,0.5);
  --shadow-glow: 0 0 30px rgba(191, 155, 48, 0.04);
}
```

### 12.2 Typography

```css
/* Labels */
.label-lg { @apply text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500; }
.label-sm { @apply text-[9px] font-semibold tracking-[0.2em] uppercase text-gray-600; }

/* Data values */
.value-lg { @apply text-2xl font-semibold text-gray-100; }
.value-md { @apply text-lg font-semibold text-gray-100; }
.value-sm { @apply text-sm font-medium text-gray-200; }

/* Body */
.body-primary { @apply text-sm text-gray-300 leading-relaxed; }
.body-secondary { @apply text-sm text-gray-500; }
.body-mono { @apply text-xs font-mono text-gray-600; }

/* Section headers */
.section-title { @apply text-sm font-semibold text-gray-400 uppercase tracking-widest; }
```

### 12.3 Spacing

```css
/* Card padding */
.card-padding { @apply p-5; }

/* Section gap */
.section-gap { @apply gap-4; }

/* Content max-width */
.content-max { @apply max-w-6xl mx-auto; }
```

### 12.4 Border Radius

```css
/* Standard */
.radius-card { @apply rounded-lg; }     /* 8px */
.radius-badge { @apply rounded; }       /* 4px */
.radius-button { @apply rounded-md; }    /* 6px */
```

---

## 13. Recommended UI Sprint Order

| Sprint | Focus | Duration | Dependencies |
|--------|-------|----------|--------------|
| 1 | Dark theme system + Shell + Navigation | 1 week | None |
| 2 | Command Center (existing components redesigned for dark theme) | 1 week | Sprint 1 |
| 3 | Radar polygon + Diagnostic state animations | 1.5 weeks | Sprint 2 |
| 4 | Timeline + Evidence popups | 1.5 weeks | Sprint 2 |
| 5 | Constellation + Playback mode | 1 week | Sprint 4 |
| 6 | Transitions + Motion polish | 1 week | Sprints 3-5 |
| 7 | Performance + Accessibility + QA | 1 week | Sprint 6 |

**Total estimated duration: 7-8 weeks for full production implementation.**

**Minimum viable launch (Sprints 1-2): 2 weeks** — Dark theme command center with all existing temporal components redesigned. No radar, timeline, or constellation yet. This is the fastest path to a cinematic dark experience with real data.

---

*This document is the design blueprint for FrictionRadar's Organizational Intelligence Platform. Implementation should follow the sprint order, with each sprint producing a reviewable increment. The cinematic quality comes from the cumulative effect of many restrained, purposeful details — not from any single spectacular effect.*