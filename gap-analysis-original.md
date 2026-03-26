# Gap Analysis: Spec vs. Codebase (Original Pre-React Analysis)

> Captured before the Streamlit-to-React migration. Useful as a baseline reference.

---

## Section 1: System Overview & Philosophy

| Requirement | Status | Gap |
|---|---|---|
| JobNimbus is source of truth, system never overrides | ✅ | — |
| Humans make all final decisions | ✅ | — |
| Court-admissible notes | ✅ Locally | Notes not pushed to JN yet |
| AI engine configurable in plain English | ✅ | — |
| Weather two-stage architecture | ⚠️ Partial | Only Stage 1 (free API) implemented |
| Scales from 20 to 200+ jobs | ⚠️ | No load testing, SQLite in dev, no pagination on job list |

---

## Section 2: JobNimbus Integration

| Requirement | Status | Gap |
|---|---|---|
| 2.2 Read customer name & address | ✅ | — |
| 2.2 Read job type (insurance/retail) | ✅ | — |
| 2.2 Read payment type (cash/finance/insurance) | ⚠️ | Finance never detected — code maps non-insurance to "cash", never "finance" |
| 2.2 Read primary trade | ✅ | — |
| 2.2 Read secondary trades | ❌ | Always set to empty [] — no JN field mapping for secondary trades |
| 2.2 Read material type | ✅ | — |
| 2.2 Read square footage | ✅ | — |
| 2.2 Read date entered system | ✅ | — |
| 2.2 Read sales rep | ✅ | — |
| 2.2 Read existing notes | ✅ | — |
| 2.2 Read documents/permit upload | ❌ | No document/permit scan from JN — only notes text is fetched |
| 2.2 Read current JN status | ✅ | — |
| 2.3 Status mapping: Pending Confirmation | ✅ | — |
| 2.3 Status mapping: Coming Soon (Permit & Order / Pending Materials) | ❌ | Only "Schedule Job" status is synced — "Permit & Order" and "Pending Materials" statuses are not monitored |
| 2.3 Status mapping: Primary Complete (Other Trades) | ❌ | No monitoring of "Other Trades" JN status — no webhook/polling for status changes after initial sync |
| 2.3 Status mapping: Completed (Job Complete) | ❌ | No monitoring of "Job Complete" JN status |
| 2.4 Push Scheduling Decision Note to JN | ❌ | Notes generated locally but never pushed to JN |
| 2.4 Push Not Built Note to JN | ❌ | Same — local only |
| 2.4 Push Secondary Trade Alert Note to JN | ❌ | Same |
| 2.4 Push Weather Rollback Note to JN | ❌ | Same |
| 2.4 Push Standalone Rule Note to JN | ❌ | Same |
| 2.4 Push Night Before Weather Note to JN | ❌ | Same |
| 2.5 Note format: server clock timestamp | ⚠️ | Uses datetime.utcnow() — spec says server clock, not UTC. Should be local TZ (Indianapolis) |
| 2.5 Note templates version-controlled in settings | ❌ | Templates are hardcoded in notes.py, not stored in settings panel |

---

## Section 3: AI Scoring Engine

| Requirement | Status | Gap |
|---|---|---|
| 3.2 Days in Queue vs Average | ✅ | — |
| 3.2 Payment Type scoring | ✅ | — |
| 3.2 Trade Type (single vs multi) | ✅ | — |
| 3.2 Geographic Proximity as scoring factor | ❌ | Proximity is NOT a deterministic scoring factor — weight_proximity exists in settings but is never used in compute_deterministic_score(). Only Claude considers it. |
| 3.2 Material vs Weather compatibility filtering | ❌ | Jobs with incompatible weather are NOT filtered before scoring as spec requires |
| 3.2 Rescheduled Counter | ✅ | — |
| 3.2 Permit Confirmed | ✅ | — |
| 3.2 Duration Confirmed | ✅ | — |
| 3.3 Plain-English rules configuration | ✅ | — |
| 3.4 Conversational/iterative interaction | ❌ | No conversational UI — system is button-driven, not a chat interface. No "ask for recalculation with adjusted parameters" |
| 3.4 Scheduler can swap jobs, adjust PM assignments and recalculate | ⚠️ | Can add/remove from plans but no inline swap or drag-and-drop |

---

## Section 4: Material Types & Duration Tiers

| Requirement | Status | Gap |
|---|---|---|
| 4.1 All material types listed | ✅ | — |
| 4.1 Wood Shake defaults Tier 3 + crew flag | ✅ | — |
| 4.1 Slate defaults Tier 3 + crew flag | ✅ | — |
| 4.1 Metal defaults Tier 3 + crew flag | ✅ | — |
| 4.1 TPO/Duro-Last/EPDM/Coatings hard confirmation gate | ✅ | Goes to Pending Confirmation |
| 4.1 Siding does not consume PM roofing capacity slot | ❌ | No siding add-on capacity logic — siding treated like any other job in scheduling |
| 4.2 Tier 1: ≤30 sq auto-confirmed | ✅ | — |
| 4.2 Tier 2: 31-60 sq yellow flag | ✅ | — |
| 4.2 Tier 3: 61+ sq RED flag, hard gate | ⚠️ | Flag exists but no hard gate preventing finalization without confirmation |
| 4.3 AI note scanning for duration signals | ✅ | — |
| 4.3 Display message: "Note from [date] references [quote]..." | ❌ | No quote-based display format — raw JSON scan result shown instead |

---

## Section 5: PM Capacity & Geographic Rules

| Requirement | Status | Gap |
|---|---|---|
| 5.1 PM roster with individual baselines | ✅ | — |
| 5.1 PM max capacity hard ceiling | ⚠️ | Max capacity stored but not enforced in scheduling — no validation prevents exceeding max |
| 5.1 PM availability per week input | ✅ | Multiselect on weekly plan page |
| 5.2 Fluid capacity: 1mi = up to 5, 2mi = up to 4, etc. | ⚠️ | Clustering assigns suggested_pm_capacity but not enforced when building plans |
| 5.2 10-25 miles: flag travel impact, suggest 2 | ⚠️ | Cluster tier exists but no travel impact warning in UI |
| 5.2 Over 40 miles: never in cluster, Standalone Rule | ✅ | — |
| 5.3 Siding add-on rule (doesn't consume capacity slot) | ❌ | Not implemented — no separate siding capacity tracking |
| 5.3 Low slope consumes full PM day, never clustered | ❌ | Not implemented — low slope jobs treated same as others in scheduling |
| 5.4 Drive time shown for cluster (not just distance) | ❌ | Only distance shown — no drive time display in cluster summaries |
| 5.5 Standalone Rule: Saturday Build option | ✅ | — |
| 5.5 Standalone Rule: Sales Rep Managed option | ✅ | — |
| 5.5 Standalone Rule: display priority score, days in queue, payment type | ❌ | Not displayed when Standalone triggers on map page |

---

## Section 6: Weather Intelligence

| Requirement | Status | Gap |
|---|---|---|
| 6.2 Stage 1 free API daily filtering | ✅ | Open-Meteo integrated |
| 6.2 Runs every morning automatically | ❌ | No automated scheduling — APScheduler in requirements but not configured |
| 6.2 Stage 1 alert if conditions change on scheduled job | ❌ | No automatic alerting — manual check only |
| 6.2 5am morning-of spot check | ❌ | Not implemented |
| 6.2 Scheduler override sends job directly to BamWx | ❌ | No BamWx integration at all |
| 6.3 BamWx final authority: 3 outcomes | ❌ | BamWx not integrated (Phase 3) |
| 6.4 Night-before automated check at configurable time | ❌ | Setting exists but no automated job |
| 6.5 Material weather thresholds configurable | ✅ | — |
| 6.5 Coating: 48hr rain window, humidity threshold, cure window | ⚠️ | Only rain window stored, no humidity or cure window thresholds |
| 6.5 TPO/EPDM: seam welding conditions | ❌ | Not tracked |

---

## Section 7: Must-Build Protocol & Not Built Workflow

| Requirement | Status | Gap |
|---|---|---|
| 7.1 Must-Build flag with deadline | ✅ | — |
| 7.1 Must-Build anchored first, week built around them | ⚠️ | Score set to 9999 but no explicit anchor-first scheduling logic |
| 7.1 System finds cluster matches around Must-Build | ❌ | No Must-Build-centered cluster search |
| 7.1 Must-Build visually distinct (color/icon) | ✅ | Yellow warning + star icon on map |
| 7.2 Not Built with reason selection | ✅ | All 7 reasons implemented |
| 7.3 Not Built ripple effect: prompt "Recalculate remaining schedule or find replacement?" | ❌ | No recalculation prompt — scores auto-recalculate but no "find replacement" option |
| 7.3 Displaced jobs get separate priority bump | ✅ | priority_bump field used |
| 7.4 Scope Change: crew locked to job | ✅ | — |
| 7.4 Scope Change: bumped jobs get Not Built - Crew Unavailable with reference | ❌ | No automatic cascade to other jobs displaced by scope change |

---

## Section 8: Secondary Trades & Job Completion Flow

| Requirement | Status | Gap |
|---|---|---|
| 8.1 Primary + secondary trade tracking | ⚠️ | Fields exist but secondary trades never populated from JN |
| 8.2 Primary Complete → secondary alert | ⚠️ | Note template exists but no automatic detection of primary completion from JN |
| 8.2 Waiting on Additional Trades with ticker | ❌ | Bucket exists but no timer/ticker running |
| 8.2 Review for Completion: all secondaries done | ❌ | No automatic transition — manual only |
| 8.3 Secondary trade aging alerts (0-6, 7-13, 14+ days) | ❌ | Settings exist (yellow/red thresholds) but no aging indicator implemented in job cards |
| 8.3 Aging based on primary_complete_date | ⚠️ | Field exists but never populated automatically |

---

## Section 9: User Interface & Map View

| Requirement | Status | Gap |
|---|---|---|
| 9.1 Bucket summary across top | ✅ | — |
| 9.1 Must-Build surfaced at top | ✅ | — |
| 9.1 Duration flags color-coded | ✅ | — |
| 9.1 Crew requirement flag most prominent | ✅ | Red bar at top of card |
| 9.1 Rescheduled counter visible | ✅ | — |
| 9.1 One-line JN note preview | ✅ | — |
| 9.1 Blocked weeks on calendar | ⚠️ | Blocked weeks in settings but no calendar view showing "days until next open window" |
| 9.2 Interactive map with job pins | ✅ | — |
| 9.2 Click pin to see job card without leaving map | ⚠️ | Popup shows summary but not full job card |
| 9.2 PM assignments as colored overlays | ✅ | — |
| 9.2 Standalone jobs visually isolated | ✅ | — |
| 9.3 7-day grid weekly plan | ✅ | — |
| 9.3 Jobs draggable between days | ❌ | No drag-and-drop — Streamlit limitation. Add/remove workflow instead |
| 9.3 PM capacity bar per day | ✅ | — |
| 9.3 Weather overlay per day | ✅ | — |
| 9.3 BamWx check on "Confirm Week" | ❌ | No BamWx — only free API check available |
| 9.3 Recalculate button during plan building | ✅ | — |
| 9.4 All 14 required job card fields | See below | |

### Job Card Fields

| Field | Status |
|---|---|
| Customer Name & Address | ✅ |
| Material Type w/ weather compat | ✅ |
| Square Footage w/ tier badge | ✅ |
| Duration (confirmed/unconfirmed) | ✅ |
| Payment Type (color coded) | ✅ |
| Trade Type (primary + secondary count) | ✅ |
| Days in Queue (vs rolling avg indicator) | ⚠️ Shows days but no above/below/at average indicator |
| Rescheduled Counter | ✅ |
| Must-Build Flag w/ deadline | ✅ |
| Crew Requirement (most prominent) | ✅ |
| JN Note Preview | ✅ |
| Standalone Rule Flag w/ buttons | ✅ |
| Weather Status | ✅ |

---

## Section 10: Settings Panel

| Requirement | Status | Gap |
|---|---|---|
| PM Roster | ✅ | — |
| Crew Roster | ✅ | — |
| PM Baseline Capacity | ✅ | — |
| Distance Rules | ✅ | — |
| Material Weather Thresholds | ✅ | — |
| BamWx Night-Before Check Time | ✅ | Setting exists (no backend automation) |
| Secondary Trade Aging Thresholds | ✅ | Setting exists (UI not implemented) |
| AI Rules (Plain English) | ✅ | — |
| Blocked Weeks | ✅ | — |
| Sit Time Average | ✅ | — |
| Note Templates (review/edit) | ❌ | Templates hardcoded in notes.py, not editable in settings |

---

## Section 11: Build Phases

| Phase | Status |
|---|---|
| Phase 1 - Core Scheduling Intelligence | ⚠️ ~85% — missing manual job entry (JN is only source), proximity scoring, conversational UI |
| Phase 2 - JobNimbus Integration | ⚠️ ~40% — reads from JN, no writes, no status monitoring beyond "Schedule Job", no webhooks |
| Phase 3 - Weather Intelligence | ❌ ~15% — Stage 1 only, no BamWx, no automated checks, no 5am spot check |
| Phase 4 - Intelligence Enhancements | ❌ ~20% — no dynamic rolling average, no secondary trade aging UI, no full standalone integration, no drag-and-drop, scope change partial |

---

## Section 12: Technical Notes

| Requirement | Status | Gap |
|---|---|---|
| 12.1 React.js frontend recommended | ❌ | Streamlit used instead — limits drag-and-drop, real-time updates, mobile UX |
| 12.1 PostgreSQL database | ⚠️ | SQLite default; docker-compose has Postgres but not active |
| 12.1 Real-time updates | ❌ | No websocket/real-time — Streamlit requires manual refresh |
| 12.1 Mobile-friendly browser access | ❌ | Streamlit is not mobile-optimized |
| 12.3 Timestamp uses server clock, not client browser | ✅ | — |
| 12.3 Geographic clustering: no neighborhood names/demographic proxies | ✅ | Only coordinates & distances |
| 12.3 Notes logged locally with full audit trail | ✅ | NoteLog model |
| 12.3 Note template version control | ❌ | template_version field exists but no versioning logic |
| 12.4 AI fallback to score-sorted list if Claude fails | ✅ | — |

---

## Summary: Critical Gaps (High Priority)

1. **No note pushing to JobNimbus** — all 6 note types are local-only
2. **No JN status monitoring beyond "Schedule Job"** — "Coming Soon", "Other Trades", "Job Complete" statuses not tracked
3. **Secondary trades never populated from JN** — always empty array
4. **Payment type "finance" never detected** — only insurance vs cash
5. **No BamWx integration** — no Stage 2 weather at all
6. **No automated weather checks** — no 5am check, no nightly check, no alerting
7. **Geographic proximity not used in deterministic scoring** — weight exists but unused
8. **Weather-incompatible jobs not pre-filtered before scoring**
9. **No secondary trade aging indicators in the UI**
10. **No manual job entry** — system requires JN; Phase 1 spec calls for manual entry first
11. **No drag-and-drop in weekly plan** (Streamlit limitation)
12. **No real-time updates or mobile-friendly UI** (Streamlit vs React)
13. **No conversational/iterative AI interaction** — spec describes chat-like recalculation
14. **Siding add-on capacity rule not implemented** (doesn't consume PM slot)
15. **Low slope full-day PM rule not implemented**
16. **Note templates not editable in settings**
17. **PM max capacity not enforced during scheduling**
18. **No Must-Build-centered cluster search**
19. **No Not Built ripple effect prompt** ("recalculate or find replacement?")
20. **No scope change cascade** (bumped jobs don't auto-receive "Crew Unavailable")
