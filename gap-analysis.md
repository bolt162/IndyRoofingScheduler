# Detailed Gap Analysis: problem.md vs Codebase (Line-by-Line)

**Date:** 2026-03-25
**Methodology:** Every requirement in problem.md verified against actual source code with file:line references.

---

## Section 1: System Overview & Philosophy (Lines 12-46)

### Line 14: "reads from JobNimbus, applies AI-driven scoring logic, and tells the scheduling team what to build and when"
- **PASS** — `backend/services/jobnimbus.py:30-34` reads from JN. `backend/services/scoring.py:94-182` runs AI scoring. Dashboard displays recommendations.

### Line 16: "writes decision-based notes back to JobNimbus"
- **FAIL** — `backend/services/jobnimbus.py:1-4` explicitly says "READ-ONLY. No data is ever written to JobNimbus." `backend/services/notes.py:2-4` says "NEVER pushed to JobNimbus until the Phase 4 toggle is enabled." Every `NoteLog` is created with `pushed_to_jn=False` (notes.py:52,77,102,124,147). **No JN write endpoint exists anywhere in the codebase.**

### Line 20: "JobNimbus is the source of truth - this system never overrides it"
- **PASS** — Read-only JN client, no status changes.

### Line 21: "Humans make all final decisions"
- **PASS** — All scheduling requires manual confirmation.

### Line 22: "All notes pushed to JN must be factual, objective, and court-admissible"
- **PARTIAL** — Note templates are factual/objective (notes.py:25-43), but notes are **never actually pushed to JN**.

### Line 23: "AI engine is configurable in plain English - no developer needed"
- **PASS** — `ai_custom_rules` setting in DB, textarea in SettingsPage.tsx:331-338, passed to Claude in scoring.py:145,255.

### Line 24: "Weather costs controlled through a two-stage API architecture"
- **FAIL** — Only Stage 1 (Open-Meteo) implemented. `weather.py:2-3` explicitly says "Stage 2 (BamWx) will be added in Phase 3." No BamWx code exists.

### Line 25: "scales from 20 jobs in winter to 200+ jobs in peak season"
- **UNTESTED** — No pagination on job queries (`jobs.py:12-16` returns all). Claude scoring limits to top 50 (scoring.py:147), but no load testing done.

### Lines 29-37: "What This System Does" table
- "Pushes Notes to JN" — **FAIL** (see Line 16 above)
- "Alerts on Secondaries" — **FAIL** — `generate_secondary_trade_alert()` exists in notes.py:84-105, but it's **never called automatically**. No trigger when JN status changes to "Other Trades". No aging alert UI on job cards.
- All other items — **PASS**

### Lines 41-46: "What This System Does NOT Do"
- **PASS** — Correctly implemented. System doesn't change JN statuses, handle comms, etc.

---

## Section 2: JobNimbus Integration (Lines 48-106)

### 2.2 Data Flow — JN to Scheduler (Lines 56-70)

| Field (spec line) | Code Location | Status | Issue |
|---|---|---|---|
| **Customer Name & Address** (58) | jobnimbus.py:88-93,141-143 | PASS | Mapped correctly |
| **Job Type** (60) | jobnimbus.py:132 | PARTIAL | Reads `record_type_name` but only gets "insurance" vs default. No explicit "retail" mapping. |
| **Payment Type** (61) | jobnimbus.py:134-135 | **WRONG** | `payment_type = "insurance" if job_type == "insurance" else "cash"` — **Finance is never set**. Spec requires Cash / Finance / Insurance. There's no JN field mapping for finance. |
| **Primary Trade** (62) | jobnimbus.py:138 | PARTIAL | Reads `Trade #1` custom field, defaults to "roofing". Doesn't validate against TradeType enum. |
| **Secondary Trades** (63) | jobnimbus.py:160 | **FAIL** | Always set to `[]` empty array. **No JN field is read for secondary trades.** |
| **Material Type** (64) | jobnimbus.py:102-105 | PARTIAL | Reads "Roof Material Type" custom field. But raw JN values like "IKO" or "OC" **won't match** our enum values (asphalt, polymer_modified, etc.). **No value mapping/normalization.** |
| **Square Footage** (65) | jobnimbus.py:109-115 | PASS | Reads "Roof Total Square", converts squares to sq ft. |
| **Date Entered System** (66) | jobnimbus.py:120-129 | PASS | Parses `date_created` unix timestamp. |
| **Sales Rep** (67) | jobnimbus.py:146 | PASS | Reads `sales_rep_name`. |
| **Existing Notes** (68) | jobnimbus.py:202-210 | PASS | Fetches via `fetch_notes_for_job()`, stored in `jn_notes_raw`. |
| **Documents — Permit** (69) | note_scanner.py:43 | PASS | AI scans for permit signals. |
| **Current JN Status** (70) | jobnimbus.py:169 | PASS | Stored from `status_name`. |

### 2.3 Status Mapping — JN to Scheduler Buckets (Lines 76-86)

| Bucket | Trigger | Status | Issue |
|---|---|---|---|
| **Pending Confirmation** (78) | "Permit & Order / Pending Materials in JN" | **FAIL** | Bucket enum exists (job.py:11) but **no trigger logic**. JN sync only fetches "Schedule Job" status jobs (jobnimbus.py:30). Jobs at "Permit & Order" or "Pending Materials" are **never fetched**. |
| **Coming Soon** (79) | "Permit & Order or Pending Materials" | **FAIL** | Same — no fetch for these JN statuses. |
| **To Schedule** (80) | "JN status = Schedule Job" | PASS | jobnimbus.py:30-34,170 correctly maps. |
| **Scheduled** (81) | Manual + decision note | PARTIAL | Works locally. Note **not pushed to JN**. |
| **Not Built** (82) | Manual flag + reason note | PARTIAL | Works locally. Note **not pushed to JN**. |
| **Primary Complete** (83) | "JN status = Other Trades" | **FAIL** | **No polling/webhook for "Other Trades" JN status.** |
| **Waiting on Trades** (84) | Auto after primary complete | **FAIL** | **No auto-transition logic.** |
| **Review for Completion** (85) | All secondaries done | **FAIL** | **No detection of secondary completion.** |
| **Completed** (86) | "JN status = Job Complete" | **FAIL** | **No polling for "Job Complete".** |

### 2.4 Data Flow — Scheduler to JN (Lines 88-97)

**ALL SIX NOTE TYPES FAIL** — Notes generated locally, never pushed to JN:
1. Scheduling Decision Note — notes.py:52 `pushed_to_jn=False`
2. Not Built Note — notes.py:77 `pushed_to_jn=False`
3. Secondary Trade Alert — notes.py:102 `pushed_to_jn=False`
4. Weather Rollback Note — notes.py:124 `pushed_to_jn=False`
5. Standalone Rule Note — notes.py:147 `pushed_to_jn=False`
6. Night Before Weather Note — **No function exists for this.**

### 2.5 Note Format Standard (Lines 99-105)

| Requirement | Status | Evidence |
|---|---|---|
| `[SCHEDULER SYSTEM - date/time]` prefix | PASS | notes.py:26 (minor: double dash `--` vs single) |
| Factual, no subjective language | PASS | |
| No demographic references | PASS | |
| Server clock timestamp | PASS | `datetime.now()` in notes.py:16 |
| Notes logged locally with audit trail | PASS | NoteLog table |
| **Templates stored in settings, version-controlled** | **FAIL** | Hardcoded in notes.py. Not editable in settings. |

---

## Section 3: AI Scoring Engine (Lines 107-152)

### 3.1 Overview (Lines 109-113)
| Requirement | Status | Evidence |
|---|---|---|
| AI explains every recommendation | PASS | scoring.py:114 stores `score_explanation` |
| Scheduler can recalculate with adjusted parameters | **FAIL** | Only full re-run via "Run Scoring" button. No parameter adjustment. |

### 3.2 Scoring Factors (Lines 115-128)

| Factor | Status | Issue |
|---|---|---|
| Days in Queue vs Average | PASS | scoring.py:34-45 |
| Payment Type | PASS | scoring.py:47-53 |
| Trade Type | PASS | scoring.py:55-60 |
| Geographic Proximity | **PARTIAL** | Weight exists but **not in `compute_deterministic_score()`**. Only sent to Claude context. |
| Material vs Weather | **FAIL** | Weight exists but **not in `compute_deterministic_score()`**. |
| Must-Build Flag | PASS | score = 9999.0 |
| Rescheduled Counter | PASS | scoring.py:74-79 |
| Permit Confirmed | PASS | scoring.py:62-66 |
| Duration Confirmed | PASS | scoring.py:68-72 |

### 3.4 Scheduler Interaction Flow (Lines 142-152)

| Step | Status | Issue |
|---|---|---|
| Input PMs and crews (146) | **PARTIAL** | PM selection works. **No crew availability input.** **No weekly PM availability.** |
| Build plan grouped by PM with cluster map (147) | **FAIL** | Returns flat list. `"clusters": []` always empty (scoring.py:178). |
| Add/remove/swap builds (148) | **PARTIAL** | Drag-and-drop. No inline swap or PM reassignment. |
| Recalculates instantly (149) | **FAIL** | Manual "Run Scoring" required. |
| BamWx on confirmed jobs (150) | **FAIL** | Not integrated. |
| Notes pushed to JN (151) | **FAIL** | Not pushed. |

---

## Section 4: Material Types & Duration Tiers (Lines 154-192)

### 4.1 Material Types (Lines 156-168)

| Material | Status | Issue |
|---|---|---|
| Asphalt (160) | PASS | |
| Polymer Modified (162) | PASS | |
| Wood Shake (163) | PASS | Tier 3 + crew flag |
| Slate (164) | PARTIAL | Crew flag set. **"Dedicated crew confirmed before scheduling" gate missing.** |
| Metal (165) | PARTIAL | **No separate wind threshold.** Uses asphalt default. |
| Siding (166) | **FAIL** | (1) No manual confirmation gate. (2) **Siding counts against PM roofing capacity.** |
| TPO/Duro-Last/EPDM/Coatings (167) | PARTIAL | Low slope gate works. **TPO/Duro-Last/EPDM share same weather settings.** |
| Other (168) | **PARTIAL** | Returns `tier_2` when sq footage=None. Spec says Tier 3. |

### 4.2 Duration Tiers (Lines 170-179)
| Tier | Status | Issue |
|---|---|---|
| Tier 1 | PASS | |
| Tier 2 | PASS | |
| Tier 3 | **PARTIAL** | **Hard gate not enforced.** Can schedule without confirmation. |
| Low Slope | **PARTIAL** | **Placed in `to_schedule` instead of `pending_confirmation`** per spec. |

### 4.3 AI Note Scanning (Lines 181-191)
- Scanning: PASS
- **Display format "Note from [date] references [quote]..."** — **FAIL** — Not rendered in spec format.

---

## Section 5: PM Capacity & Geographic Rules (Lines 194-239)

### 5.1 Settings (Lines 196-204)
- All PASS except **PM Availability by Week** — **FAIL** (no weekly availability input).

### 5.2 Fluid Capacity (Lines 206-216)
- **PASS** — 5 cluster tiers match spec.

### 5.3 Siding Add-On Rule (Lines 218-224)
- **FAIL** — Siding counted same as roofing. No "3 roofing + 1 siding" display. Low slope doesn't consume full PM day.

### 5.4 Drive Time Clustering (Lines 226-231)
- **PARTIAL** — Calculated in backend. **Never displayed to user.**

### 5.5 Standalone Rule (Lines 232-239)
- **FAIL** — Flag exists. **No Saturday Build / Sales Rep Managed UI buttons.** No selection workflow.

---

## Section 6: Weather Intelligence (Lines 241-281)

### 6.2 Stage 1 (Lines 247-255)
| Requirement | Status |
|---|---|
| Filters no-go days | PASS |
| **Runs automatically every morning** | **FAIL** — No background scheduler. Manual only. |
| **Fires alert on condition change** | **FAIL** — No alert system. |
| **Override → BamWx** | **FAIL** — BamWx missing. |
| **5am spot check** | **FAIL** — No scheduler. |

### 6.3 Stage 2 — BamWx (Lines 257-265)
- **ALL FAIL** — Not implemented. "Do Not Build automatically moves to Not Built" — **not implemented** (weather check updates field but never auto-transitions bucket).

### 6.4 Night-Before Check (Lines 267-269)
- **FAIL** — Setting exists, nothing acts on it.

### 6.5 Thresholds (Lines 271-281)
| Issue | Detail |
|---|---|
| TPO/EPDM 24hr rain window | Checks daily precip only, not 24-hour window |
| Coatings humidity/cure window | **Not implemented** |
| Wood shake/slate/metal thresholds | **Not in settings** — default to asphalt |
| Seam welding for TPO/EPDM | **Not tracked** |

---

## Section 7: Must-Build & Not Built (Lines 283-324)

### 7.1 Must-Build (Lines 285-295)
- Mostly PASS. **Note not pushed to JN.**

### 7.2 Not Built (Lines 297-308)
- All 7 reasons: PASS. **"Other" doesn't require text input.**

### 7.3 Ripple Effect (Lines 310-314)
- **FAIL** — No "Recalculate or find replacement?" prompt. No recalculate button.

### 7.4 Scope Change (Lines 316-324)
| Requirement | Status | Issue |
|---|---|---|
| Multi-Day flag | **PARTIAL** | `is_multi_day` **not set to True** in scope change flow. |
| Crew retained | PARTIAL | Checkbox exists. `assigned_crew_id` **not preserved** in backend. |
| **Day 2+ near-Must-Build** | **FAIL** | Standard bump only. |
| **Cascading Not Built for displaced jobs** | **FAIL** | Not implemented. |

---

## Section 8: Secondary Trades (Lines 326-357)

### 8.2 Status Flow (Lines 337-346)
- Auto-transitions (Primary Complete → Waiting → Review → Completed): **ALL FAIL**
- `generate_secondary_trade_alert()` **never called by any trigger.**
- No "Mark Complete" button for Review for Completion jobs.

### 8.3 Aging Alerts (Lines 348-357)
- **ALL FAIL** — No yellow/red visual indicators in UI. Settings exist but unused.

---

## Section 9: UI & Map (Lines 359-413)

### 9.1 Dashboard (Lines 361-371)
| Missing | Detail |
|---|---|
| JN note preview on job cards | Not displayed anywhere |
| Blocked weeks on calendar | No calendar view on dashboard |
| Crew req not "MOST PROMINENT" | Orange border is subtle vs red must-build ring |

### 9.2 Map (Lines 373-383)
| Missing | Detail |
|---|---|
| Cluster color-coded groupings | Colors by bucket, not cluster |
| Confirmed jobs distinct pin | Same green for all scheduled |

### 9.3 Weekly Plan (Lines 385-394)
| Missing | Detail |
|---|---|
| Blocked days marked | Not displayed |
| Weather overlay per day | Component exists, **never rendered** in DayColumn |
| BamWx on Confirm Week | Not integrated |
| Recalculate button | Missing entirely |

### 9.4 Job Card (Lines 396-413)
| Missing | Detail |
|---|---|
| Payment type color-coded | Plain text only |
| Days in Queue vs average indicator | Raw number, no comparison |
| JN Note Preview | Not displayed |
| Standalone Rule buttons | Text badge only, no Saturday/Sales Rep buttons |

---

## Section 10: Settings (Lines 415-430)
- Most PASS. **Note Templates (line 430) — FAIL — hardcoded, not editable.**
- Blocked weeks: text input only, not shown in calendar/queue view.

---

## Section 11: Build Phases (Lines 432-481)

### Phase 1 Gaps
- **Manual job entry form** — FAIL (no create endpoint or UI form)

### Phase 2 Gaps
- **Note pushing to JN** — FAIL
- **Status monitoring** — FAIL

### Phase 3 Gaps
- **ALL items FAIL** — BamWx, nightly check, Scheduler Decision, 5am check

### Phase 4 Gaps
- **Dynamic rolling average** — FAIL (static only)
- **Secondary trade aging alerts** — FAIL (no UI)
- **Standalone Rule fully integrated** — FAIL
- Customer communication flag at 2+ reschedules — PARTIAL (text only)

---

## Section 12: Technical Notes (Lines 483-548)

### BUG: Scoring Weight Key Mismatch
- Frontend SettingsPage.tsx:213-220 uses keys: `score_weight_days_in_queue`, `score_weight_payment_type`, etc.
- Backend settings.py:61-68 uses keys: `weight_days_in_queue`, `weight_payment_type`, etc.
- **These don't match — UI changes to scoring weights have ZERO effect on actual scoring.**

### Other Issues
- AI scoring returns flat list, not PM-grouped results
- Rolling average sit time not sent to Claude context
- Weather for target dates not proactively fetched during scoring

---

## MASTER ISSUE LIST (44 Items)

### CRITICAL (8)
1. Notes never pushed to JobNimbus (6 note types, always `pushed_to_jn=False`)
2. BamWx Stage 2 weather entirely missing (placeholder only)
3. No background scheduler (morning checks, 5am, night-before, JN polling)
4. No JN status change monitoring (Other Trades, Job Complete, Pending Materials)
5. Secondary trade aging alerts not rendered in UI
6. No manual job entry form (Phase 1 requirement)
7. Standalone Rule has no Saturday Build / Sales Rep Managed UI
8. Note templates not editable in settings (hardcoded)

### MAJOR (17)
9. Payment type mapping: "finance" never assigned from JN
10. Secondary trades always `[]` — never read from JN
11. Material type not normalized (raw JN values won't match enums)
12. Scoring: proximity + material-weather weights not in deterministic scorer
13. Scoring returns flat list, not PM-grouped with cluster map
14. No instant recalculation on adjustments
15. No "Recalculate or find replacement?" prompt after Not Built
16. No Recalculate button on Weekly Plan
17. Siding add-on rule: doesn't exclude from PM roofing capacity
18. Low slope doesn't consume full PM day
19. Drive time calculated but never displayed in UI
20. Weather overlay not rendered in Weekly Plan DayColumn
21. Blocked weeks not shown on calendar/plan views
22. Low slope jobs placed in `to_schedule` instead of `pending_confirmation`
23. Auto-transitions broken (Primary Complete -> Waiting -> Review)
24. PM weekly availability input missing
25. **Scoring weight key mismatch between frontend and backend (BUG)**

### MINOR (19)
26. JN note preview not on job card
27. Days in Queue: no above/below/at average indicator
28. Payment type not color-coded on job card
29. Crew requirement not MOST PROMINENT visually
30. Map: clusters not color-coded by grouping
31. Map: confirmed jobs no distinct pin state
32. Scope change doesn't set `is_multi_day=True`
33. Multi-day Day 2+ not near-Must-Build priority
34. Cascading Not Built for crew reallocation missing
35. Duration scan display format doesn't match spec
36. Slate: no dedicated crew confirmation gate
37. Metal: no separate wind threshold
38. TPO/Duro-Last/EPDM share same weather settings
39. Coatings: humidity and cure window not tracked
40. Wood shake/slate/metal: no separate weather thresholds in settings
41. "Other" Not Built reason doesn't require text input
42. Dynamic rolling average sit time not auto-calculated
43. Tier 3 hard gate not enforced (can schedule unconfirmed)
44. Crew availability not inputtable per scoring run

---

**Total Requirements Verified: ~170**
**PASS: ~85 (~50%)**
**PARTIAL: ~30 (~18%)**
**FAIL: ~55 (~32%)**
