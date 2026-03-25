**INDY ROOF & RESTORATION**

**SCHEDULING INTELLIGENCE SYSTEM**

_Product Specification Document_

Version 1.0 | Prepared for Developer Handoff | March 2026

| Company<br><br>**Indy Roof & Restoration**<br><br>Website<br><br>**<www.indyroofandrestoration.com>** | Primary User<br><br>**Operations / Scheduling Team**<br><br>CRM Integration<br><br>**JobNimbus (Open API)** |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |

# **1\. System Overview & Philosophy**

The Indy Roof & Restoration Scheduling Intelligence System is a web-based application designed to eliminate manual scheduling complexity during peak season. It is not a replacement for JobNimbus - it is a smart recommendation layer that reads from JobNimbus, applies AI-driven scoring logic, and tells the scheduling team what to build and when.

JobNimbus remains the system of record. All job data, customer information, status changes, and scheduling actions continue to live in JobNimbus. This system reads that data, applies intelligence, and writes decision-based notes back to JobNimbus. It never changes statuses autonomously.

### **Core Principles**

- JobNimbus is the source of truth - this system never overrides it
- Humans make all final decisions - the system recommends, never dictates
- All notes pushed to JobNimbus must be factual, objective, and court-admissible
- The AI engine is configurable in plain English - no developer needed for rule changes
- Weather costs are controlled through a two-stage API architecture
- The system scales from 20 jobs in winter to 200+ jobs in peak season

### **What This System Does**

| **Reads from JN**           | Job data, trade types, payment type, material type, square footage, notes, permit status, date entered |
| --------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Scores & Ranks**          | Applies weighted AI scoring across all open jobs in the queue                                          |
| **Clusters Geographically** | Groups jobs by driving proximity for PM efficiency                                                     |
| **Recommends Builds**       | Suggests optimal daily and weekly build plans based on crew and PM inputs                              |
| **Monitors Weather**        | Daily free API checks plus BamWx night-before final authority                                          |
| **Manages Exceptions**      | Must-Build protocol, Not Built workflow, Standalone Rule                                               |
| **Pushes Notes to JN**      | Writes decision-based, timestamped, court-admissible notes back to JN                                  |
| **Alerts on Secondaries**   | Fires alerts when primary trade completes and secondary trades remain open                             |

### **What This System Does NOT Do**

- Change job statuses in JobNimbus
- Replace or duplicate JobNimbus functionality
- Handle customer communications
- Manage invoicing, commissions, or financials
- Automatically schedule without human confirmation
- Serve any user other than the ops/scheduling team

# **2\. JobNimbus Integration**

## **2.1 Integration Philosophy**

The integration is intentionally narrow and low-risk. The system reads specific data fields and listens for specific status changes. It writes only notes. It never modifies job records, contacts, statuses, or financial data. This boundary ensures that if the integration has a technical issue, nothing in JobNimbus is affected.

## **2.2 Data Flow - JN to Scheduler**

The following JobNimbus fields are read via the open API when a job reaches "Schedule Job" status:

| **Customer Name & Address** | Used for map plotting, proximity clustering, and note attribution                         |
| --------------------------- | ----------------------------------------------------------------------------------------- |
| **Job Type**                | Insurance vs Retail - affects scoring priority                                            |
| **Payment Type**            | Cash / Finance / Insurance - key scoring factor                                           |
| **Primary Trade**           | Roofing, siding, gutters, windows, paint, interior, other                                 |
| **Secondary Trades**        | All additional trades attached to the job                                                 |
| **Material Type**           | Asphalt, Polymer Modified, TPO, Duro-Last, EPDM, Coating, Wood Shake, Slate, Metal, Other |
| **Square Footage**          | Used for duration tier classification                                                     |
| **Date Entered System**     | Used for sit time scoring                                                                 |
| **Sales Rep**               | Pre-populated for Standalone Rule - Sales Rep Managed option                              |
| **Existing Notes**          | Scanned by AI for duration hints, permit status, customer requirements, crew notes        |
| **Documents**               | Permit upload confirmed via note scan                                                     |
| **Current JN Status**       | Determines which scheduler bucket the job belongs in                                      |

## **2.3 Status Mapping - JN to Scheduler Buckets**

The scheduler monitors the following JobNimbus production statuses and maps them to internal buckets:

| **Status / Bucket**   | **Description**                                                             | **Trigger**                              | **JN Push**                |
| --------------------- | --------------------------------------------------------------------------- | ---------------------------------------- | -------------------------- |
| Pending Confirmation  | Low slope, specialty materials - awaiting manual duration/crew confirmation | Permit & Order / Pending Materials in JN | No                         |
| Coming Soon           | Approved, materials ordered, not yet at Schedule Job status                 | Permit & Order or Pending Materials      | No                         |
| To Schedule           | Ready to be planned - enters scoring engine                                 | JN status = Schedule Job                 | No                         |
| Scheduled             | Plan confirmed, team executing in JN                                        | Manual - team schedules in JN            | Yes - decision note        |
| Not Built             | Returned to queue with reason and elevated priority                         | Manual flag in scheduler                 | Yes - reason note          |
| Primary Complete      | Primary trade done, secondary trades open                                   | JN status = Other Trades                 | Yes - secondary alert note |
| Waiting on Trades     | Primary done, secondary trades in progress                                  | Automatic after primary complete         | No                         |
| Review for Completion | All trades done, pending final human review                                 | All secondaries marked done              | Yes - completion flag note |
| Completed             | Manually marked complete by team                                            | JN status = Job Complete                 | No - JN drives this        |

## **2.4 Data Flow - Scheduler to JN**

The scheduler writes notes to JobNimbus in the following scenarios. Notes are always system-labeled, timestamped, factual, and court-admissible. The system never changes statuses.

- Scheduling Decision Note - when a build plan is confirmed
- Not Built Note - when a job is returned to queue, including reason
- Secondary Trade Alert Note - when primary trade completes and secondaries remain open
- Weather Rollback Note - when a scheduled job is removed due to weather change
- Standalone Rule Note - when Saturday build or Sales Rep Managed is selected
- Night Before Weather Note - BamWx result pushed to job file for record

## **2.5 Note Format Standard**

All system-generated notes follow this format to ensure clarity, consistency, and legal defensibility:

**Example - Scheduling Decision Note**

_\[SCHEDULER SYSTEM - March 19 2026 9:42am\] Job selected for scheduling on March 21. Scoring factors: 52 days in queue (avg 38 days), cash payment type, single trade roofing, asphalt material - forecast clear 58F. Proximity cluster: 3 jobs within 1.4 driving miles, northwest Indianapolis. Must-Build anchor: No. Assigned PM: \[Name\]. Duration: 1 day confirmed. Note generated automatically by Indy Roof Scheduling System._

# **3\. AI Scoring Engine**

## **3.1 Overview**

The scoring engine is powered by an AI language model (Anthropic Claude API). Rather than hardcoded rules that require developer changes, the engine accepts plain-English rules configured by the ops team. The AI receives the full job queue, available crew and PM inputs, configured rules, and weather data, then returns ranked recommendations with written explanations.

The AI explains every recommendation. The scheduler can see exactly why a job was ranked where it was, disagree, and ask for a recalculation with adjusted parameters.

## **3.2 Scoring Factors**

The following factors are weighted in the scoring engine. Weights are adjustable in the settings panel:

| **Days in Queue vs Average** | Jobs sitting longer than the rolling average score higher. Average is calculated dynamically from historical data and adjusts seasonally automatically. |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Payment Type**             | Cash and Finance score higher than Insurance. System gets paid faster on non-insurance jobs - this directly impacts cash flow.                          |
| **Trade Type**               | Single trade jobs score higher than multi-trade. Simpler execution, faster completion.                                                                  |
| **Geographic Proximity**     | Jobs that cluster tightly with other open jobs score higher. Driving distance calculated via Google Maps API.                                           |
| **Material vs Weather**      | Jobs whose material type is compatible with the forecast window score higher. Incompatible jobs are filtered before scoring.                            |
| **Must-Build Flag**          | Overrides all other scoring. Must-Build jobs are anchored first and everything else builds around them.                                                 |
| **Rescheduled Counter**      | Jobs returned to queue multiple times receive a priority bump. Displaced jobs (caused by another job's scope change) receive an immediate bump.         |
| **Permit Confirmed**         | Jobs with confirmed permit notes in JN score higher than those without.                                                                                 |
| **Duration Confirmed**       | Jobs with confirmed duration score higher than unconfirmed - reduces mid-week surprises.                                                                |

## **3.3 Plain-English Rules Configuration**

The settings panel includes a rules input area where the ops team can type custom scoring rules in plain English. The AI reads these on every scoring run. No developer is needed to add or change rules. Examples:

- "During storm season, prioritize insurance jobs in zip codes with recent hail activity"
- "If a job has been sitting more than 90 days, treat it as a cash job for scoring purposes"
- "Never suggest wood shake jobs between November and February"
- "Flag any job where the customer has called more than twice - elevate priority"
- "Do not schedule in Bloomington the same week as Lafayette - too much PM spread"

These rules are stored in the settings panel and applied to every scoring run until changed or removed.

## **3.4 Scheduler Interaction Flow**

The system is conversational and iterative, not a one-shot report. The workflow is:

- Scheduler opens app and inputs available PMs and crews for the day or week
- System runs scoring engine and returns recommended build plan grouped by PM with cluster map
- Scheduler reviews - can add builds, remove builds, swap jobs, or adjust PM assignments
- System recalculates based on adjustments instantly
- BamWx final weather check runs on confirmed jobs
- Scheduler confirms plan - decision notes pushed to JN automatically
- Scheduler goes to JN and executes the schedule (status changes done manually in JN)

# **4\. Material Types & Duration Tiers**

## **4.1 Material Types**

Every job is tagged with a material type. Material type drives two things: weather threshold filtering and crew requirement signals. Thresholds are configurable in settings - not hardcoded.

| **Asphalt Shingles**                  | Most common. Temperature floor applies (default 40F). Standard weather filtering. Covered by duration tier rules.                                                                               |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Polymer Modified**                  | Winter-viable. Lower temperature floor. Flag in settings defines threshold.                                                                                                                     |
| **Wood Shake**                        | Specialty. Defaults to Tier 3 duration (manual confirmation required). Crew requirement flag triggered.                                                                                         |
| **Slate**                             | Specialty. Defaults to Tier 3. Crew requirement flag triggered automatically. Dedicated crew must be confirmed before scheduling.                                                               |
| **Metal**                             | Specialty. Defaults to Tier 3. Crew requirement flag triggered. Wind threshold more sensitive than shingles.                                                                                    |
| **Siding**                            | Falls in steep slope non-shingle category. Manual confirmation required. Does not consume PM roofing capacity slot.                                                                             |
| **TPO / Duro-Last / EPDM / Coatings** | Low slope category. Hard confirmation gate - does not enter schedulable pool until PM manually confirms duration, crew, and conditions. Each has its own weather threshold profile in settings. |
| **Other**                             | Open text field. Treated as Tier 3 until confirmed. Ops team defines weather threshold manually.                                                                                                |

## **4.2 Duration Confidence Tiers**

Duration tiers apply to roofing jobs. All other trades (siding, low slope, specialty) require manual confirmation regardless of size.

| **Tier**  | **Condition**                                        | **Default Duration**        | **Flag**                       | **Gate**                                             |
| --------- | ---------------------------------------------------- | --------------------------- | ------------------------------ | ---------------------------------------------------- |
| Tier 1    | Residential shingles, 30 sq or under                 | 1 day - auto-confirmed      | None                           | None - flies through                                 |
| Tier 2    | Residential shingles, 31-60 sq                       | 1 day (or note-derived)     | DURATION UNCONFIRMED (yellow)  | Soft - can schedule, visible flag                    |
| Tier 3    | Residential shingles, 61+ sq, no notes               | 1 day assumed               | **DURATION UNCONFIRMED (RED)** | Hard - cannot finalize without confirmation          |
| Low Slope | TPO, Duro-Last, EPDM, Coatings, any flat roof system | None - must be set manually | PENDING CONFIRMATION           | Hard - sits in Pending Confirmation, not schedulable |

## **4.3 AI Note Scanning for Duration**

When a job enters the system, the AI scans all JN notes for duration signals. If found, the system adopts the note-derived duration but keeps the Unconfirmed flag visible for human validation. Signals the AI looks for include:

- "2 day job", "two day build", "will need 2 days", "multi-day", "multiple days"
- "Redeck" or "redeck likely" - auto-flags as likely multi-day even without a number
- "Large job", "big project" - escalates to Tier 2 minimum regardless of square footage
- Any mention of structural work, decking, framing, or tear-off complications
- "Day 1 and Day 2" or any sequenced day reference

When a duration signal is found, the system displays: "Note from \[date\] references \[quote\] - duration set to \[X days\], Unconfirmed. Please validate before finalizing schedule."

# **5\. PM Capacity & Geographic Rules**

## **5.1 Configurable Settings**

All PM capacity settings live in the settings panel and can be changed by the ops team at any time without developer involvement:

| **Number of Active PMs**           | Add or remove PMs as team changes. Each PM can have an individual name and baseline.                       |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Baseline Builds Per PM Per Day** | Default: 3. Adjustable globally or per individual PM.                                                      |
| **Maximum Builds Per PM Per Day**  | Hard ceiling. System will not suggest above this without manual override.                                  |
| **Per-PM Override**                | Set individual PM baselines that differ from team default (e.g., senior PM handles 4, newer PM handles 2). |
| **PM Availability by Week**        | Before generating weekly plan, scheduler inputs which PMs are available and any partial-week constraints.  |

## **5.2 Fluid Capacity Logic**

Baseline is 3 roofing builds per PM within reasonable distance. The system adjusts dynamically based on proximity:

| **Within 1 mile (all jobs)**  | System suggests up to 5 - flags as tight cluster opportunity          |
| ----------------------------- | --------------------------------------------------------------------- |
| **Within 2 miles (all jobs)** | System suggests up to 4                                               |
| **Within 10 miles**           | Standard baseline of 3 applies                                        |
| **10-25 miles**               | System flags travel impact, suggests reducing to 2 builds for that PM |
| **25-40 miles**               | System suggests 1-2 builds maximum, flags as outlier cluster          |
| **Over 40 miles**             | Never suggested as part of a cluster - Standalone Rule triggered      |

## **5.3 Siding Add-On Rule**

Siding jobs do not consume a PM's roofing capacity slot. A PM running 3 roofing builds can absorb a nearby siding job as an add-on. The system displays this clearly in the recommendation:

_"PM 1 - 3 roofing builds + 1 siding (siding does not impact roofing capacity)"_

Low slope jobs consume a PM's full day and are never clustered with other build types. The system treats low slope as a dedicated PM day.

## **5.4 Drive Time Clustering**

Proximity is calculated using actual driving distance via Google Maps API - not straight-line distance. This matters especially in outlying service areas like Bloomington, Lafayette, and Muncie where highways and geography affect real drive times.

When the system surfaces a cluster recommendation, it shows the scheduler the total estimated drive time between all jobs in that cluster - not just the distance. A 1.2-mile cluster that requires crossing a highway interchange is treated differently than a true neighborhood cluster.

## **5.5 Standalone Rule**

Triggered when a job has no viable cluster partners within 40 miles, or when a high-priority job (cash, significantly aged, Must-Build) needs to move regardless of proximity. The system presents two options:

- Saturday Build - crew goes out Saturday, does not impact weekday PM cluster schedule. Still runs full BamWx weather check.
- Sales Rep Managed Build - job's originating sales rep (pre-populated from JN) covers PM duties. Does not consume any PM capacity. Scheduler can override and assign a different rep.

When Standalone Rule triggers, the system also displays the job's priority score, days in queue, and payment type so the scheduler can make an informed decision about urgency.

# **6\. Weather Intelligence**

## **6.1 Two-Stage Architecture**

Weather intelligence uses two services in sequence to maximize accuracy while controlling BamWx API costs. BamWx is called only at decision-critical moments - never on idle queue jobs.

## **6.2 Stage 1 - Free Weather API (Filtering Layer)**

Used during the recommendation and daily monitoring phases. Applied across all scheduled jobs without BamWx cost. Recommended service: OpenWeatherMap or Weather.gov API.

- Filters obvious no-go days during scoring - heavy rain, temps below material thresholds, high winds
- Runs every morning automatically on all scheduled jobs
- If conditions change on a scheduled job, fires an alert to the scheduler
- Scheduler can override a Stage 1 flag - override sends the job directly to BamWx for final check
- 5am morning-of spot check on all next-day builds as a final free sanity check

## **6.3 Stage 2 - BamWx (Final Authority)**

Called only at two specific moments: final plan confirmation and the night-before automated check. Returns one of three outcomes:

| **Outcome**            | **Meaning**                                              | **System Action**                                                                                                   |
| ---------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Clear to Build**     | All conditions favorable for material type and build day | Green indicator on job card. No action required.                                                                    |
| **Do Not Build**       | Conditions do not meet threshold for material type       | Automatically moves job to Not Built. Pre-fills reason as Weather. Pushes note to JN. Alerts scheduler immediately. |
| **Scheduler Decision** | Marginal conditions - human judgment required            | Presents full forecast detail. Scheduler clicks Include or Exclude. Decision is logged and pushed to JN either way. |

## **6.4 Night-Before Automated Check**

Every evening at a configurable time (default 8:00pm, adjustable in settings), the system automatically runs all next-day builds through BamWx. No human trigger required. Results are available for the scheduler to review first thing in the morning. Do Not Build results trigger an immediate alert regardless of time.

## **6.5 Material Weather Thresholds**

Each material type has a configurable weather threshold profile in the settings panel. Defaults are provided but all values are editable by the ops team without developer involvement:

| **Asphalt Shingles**           | Min temp: 40F. No rain. Wind under 20mph.                                                   |
| ------------------------------ | ------------------------------------------------------------------------------------------- |
| **Polymer Modified**           | Min temp: 20F. No rain. Wind under 20mph.                                                   |
| **TPO / EPDM**                 | Min temp: 40F. No rain within 24hrs. Wind under 15mph. Seam welding conditions apply.       |
| **Coatings**                   | Min temp: 50F. No rain within 48hrs. Humidity threshold applies. Cure window must be clear. |
| **Wood Shake / Slate / Metal** | Configurable. Default same as asphalt until ops team defines specific thresholds.           |
| **Siding**                     | Configurable. Wind sensitivity higher than roofing - default wind max 15mph.                |

# **7\. Must-Build Protocol & Not Built Workflow**

## **7.1 Must-Build Protocol**

The Must-Build flag is a priority override that supersedes all scoring. It is used for time-sensitive jobs - real estate deals, customer deadlines, commitments made by the sales team, or any situation where a job must be completed by a specific date regardless of its normal score.

- Any job in the To Schedule bucket can be flagged as Must-Build by the ops team
- A deadline date is required when flagging - the system uses this to calculate urgency
- Must-Build jobs are anchored first in the recommendation - the week is built around them
- System finds best cluster matches around the Must-Build anchor job
- If a Must-Build has no cluster partners within 40 miles, Standalone Rule triggers automatically
- Must-Build jobs are visually distinct on the job card and map - separate color/icon
- A scheduling note explaining the Must-Build reason is pushed to JN when the plan is confirmed

## **7.2 Not Built Workflow**

When a scheduled job cannot be completed as planned, the scheduler marks it as Not Built. The job returns to the To Schedule queue with elevated priority and a reason on record. The scheduler selects from the following reason list:

| **Weather - Pre-Build** | Caught before crew went out. Forecast made build impossible.                                                                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Weather - Mid-Build** | Crew started, weather turned, had to stop. Job may have partial completion noted.                                                                     |
| **Scope Change**        | Build started and discovered to be larger than estimated (e.g., redeck required). Job converted to multi-day. Crew retained.                          |
| **Crew Unavailable**    | Crew pulled to cover another job or scope change elsewhere. Other affected jobs also receive Not Built - Crew Unavailable note referencing the cause. |
| **Material Issue**      | Problem with materials on site - wrong product, damaged delivery, shortage.                                                                           |
| **Customer Related**    | Customer cancelled, not home, HOA issue, access problem, or similar.                                                                                  |
| **Other**               | Open text field required. Ops team describes the reason.                                                                                              |

## **7.3 Not Built Ripple Effect**

When a job is marked Not Built, the system immediately prompts: "1 job removed from this week's plan. Recalculate remaining schedule or find a replacement build?" One button triggers a full recalculation around remaining jobs and available crews.

Jobs displaced by another job's scope change receive an automatic priority bump - separate from the normal sit-time scoring - because they were actively pushed out through no fault of their own.

## **7.4 Scope Change - Multi-Day Conversion**

When a job is marked Not Built with reason Scope Change, the following happens automatically:

- Job is flagged as Multi-Day - In Progress
- Crew assignment is retained - the same crew is locked to this job
- System prompts for revised total duration estimate
- Day 2 (and any additional days) are treated as a near-Must-Build - high priority, same crew, scheduled as soon as possible
- Any jobs bumped due to crew reallocation receive Not Built - Crew Unavailable with a reference to the scope change address

# **8\. Secondary Trades & Job Completion Flow**

## **8.1 Trade Types**

Every job has one primary trade and any number of secondary trades. The primary trade drives scheduling. Secondary trades are tracked for completion alerting and cash flow management.

- Primary trade options: Roofing, Siding, Gutters, Windows, Paint, Interior, Other
- Secondary trade options: Any of the above not designated as primary
- Most jobs will have roofing as primary - but any trade can be primary
- Example: A siding-primary job with windows and gutters as secondaries

## **8.2 Job Status Flow**

| **Status / Bucket**          | **Description**                                            | **Trigger**                                         | **JN Push**                            |
| ---------------------------- | ---------------------------------------------------------- | --------------------------------------------------- | -------------------------------------- |
| To Schedule                  | Job approved in JN, materials ready, enters scoring pool   | JN status: Schedule Job                             | No                                     |
| Scheduled                    | Plan confirmed by scheduler, team executing in JN          | Scheduler confirms plan                             | Yes - decision note                    |
| Primary Complete             | Primary trade marked done in JN                            | JN status: Other Trades or Job Complete             | Yes - secondary alert if trades remain |
| Waiting on Additional Trades | Primary done, secondary trades in progress, ticker running | Automatic on primary complete with open secondaries | No                                     |
| Review for Completion        | All trades marked done, pending final human sign-off       | All secondaries marked complete                     | Yes - completion flag note             |
| Completed                    | Manually confirmed complete - moves to billing in JN       | Manual confirmation by ops team                     | No - JN drives billing                 |

## **8.3 Secondary Trade Aging Alerts**

Once a job enters Waiting on Additional Trades, a visual aging indicator appears on the job card. The timer starts when the primary trade is marked complete:

| **0-6 Days**  | Normal - no flag. Ticker visible but no alert.                                                             |
| ------------- | ---------------------------------------------------------------------------------------------------------- |
| **7-13 Days** | Yellow flag - passive alert. Secondary trades overdue for attention.                                       |
| **14+ Days**  | Red flag - active alert. Escalated visibility. This represents floating money that needs to be closed out. |

Thresholds are configurable in settings. The financial reasoning: a completed roof with pending siding sitting for three weeks is revenue earned but not collectible. The aging alerts turn passive tracking into active prompts.

# **9\. User Interface & Map View**

## **9.1 Main Dashboard**

The main dashboard is the primary daily working view for the ops/scheduling team. It is designed for speed and clarity - the scheduler should be able to understand the full picture within seconds of opening the app.

- Bucket summary across top: To Schedule count, Scheduled count, Waiting on Trades count, Review for Completion count
- Must-Build jobs surfaced immediately at top of To Schedule bucket - visually distinct
- Duration flags visible on every job card - color coded by tier
- Crew requirement flag most prominent element on job cards that have one
- Rescheduled counter visible on job card - how many times returned to queue
- One-line JN note preview on each job card showing most relevant scheduler-facing note
- Blocked weeks visible on calendar - shows days until next open scheduling window

## **9.2 Map View**

All open jobs are plotted on an interactive map. The map is a core tool, not a secondary feature.

- Every job in the To Schedule bucket is pinned on the map
- Must-Build jobs use a distinct pin color/icon
- Proximity clusters are highlighted automatically - color-coded groupings
- Scheduler can click any pin to see job card summary without leaving the map
- When a weekly plan is being built, confirmed jobs show as a different pin state
- Standalone Rule jobs (over 40 miles from everything) are visually isolated on the map
- PM assignments shown as colored overlays when a plan is being reviewed

## **9.3 Weekly Plan View**

The weekly planning view allows the scheduler to build and adjust a full week of builds at once rather than day by day.

- 7-day grid with blocked days/weeks clearly marked
- Jobs draggable between days within the week
- PM capacity bar visible per day - fills as jobs are assigned
- Weather overlay on each day - Stage 1 free API flags visible at day level
- BamWx check triggered when scheduler clicks "Confirm Week"
- Recalculate button available at any point during plan building

## **9.4 Job Card - Required Fields**

Each job card must display the following information in a scannable format:

| **Customer Name & Address** | Primary identifier                                                          |
| --------------------------- | --------------------------------------------------------------------------- |
| **Material Type**           | With weather compatibility indicator for scheduled date                     |
| **Square Footage**          | With duration tier badge                                                    |
| **Duration**                | Confirmed / Unconfirmed (yellow) / Unconfirmed (RED) / Pending Confirmation |
| **Payment Type**            | Cash / Finance / Insurance - color coded                                    |
| **Trade Type**              | Primary trade + secondary trade count                                       |
| **Days in Queue**           | With indicator vs rolling average (above/below/at average)                  |
| **Rescheduled Counter**     | Number of times returned to queue                                           |
| **Must-Build Flag**         | With deadline date if flagged                                               |
| **Crew Requirement**        | MOST PROMINENT element if specialty crew required                           |
| **JN Note Preview**         | One-line summary of most relevant scheduler-facing note                     |
| **Standalone Rule Flag**    | If triggered - with Saturday or Sales Rep option buttons                    |
| **Weather Status**          | Current Stage 1 status for scheduled jobs                                   |

# **10\. Settings Panel**

The settings panel is accessible only to the ops team and controls all configurable system behavior without requiring developer involvement.

| **PM Roster**                        | Add, remove, rename PMs. Set individual capacity baselines.                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- |
| **Crew Roster**                      | Add, remove, rename crews. Flag specialty capabilities (framer, slate, TPO, etc.).                |
| **PM Baseline Capacity**             | Global default builds per PM per day.                                                             |
| **Distance Rules**                   | Proximity thresholds for cluster tiers (currently: 1mi / 2mi / 10mi / 40mi).                      |
| **Material Weather Thresholds**      | Per-material temperature, wind, and precipitation limits.                                         |
| **BamWx Night-Before Check Time**    | Default 8:00pm. Configurable.                                                                     |
| **Secondary Trade Aging Thresholds** | Yellow flag day count (default 7). Red flag day count (default 14).                               |
| **AI Rules (Plain English)**         | Free-text rules input. Applied to every scoring run.                                              |
| **Blocked Weeks**                    | Mark weeks as unavailable for scheduling. Shows in calendar and queue view.                       |
| **Sit Time Average**                 | Displays current rolling average. Can be manually seeded if historical data is limited at launch. |
| **Note Templates**                   | Review and edit the standard note templates pushed to JN for each scenario.                       |

# **11\. Recommended Build Phases**

The system is designed to be built in phases. Each phase delivers standalone value and the next phase layers on top. This prevents the project from stalling and ensures the ops team has a working tool as early as possible.

## **Phase 1 - Core Scheduling Intelligence**

Target: Working tool the ops team can use for daily recommendations.

- Manual job entry (no JN integration yet)
- AI scoring engine with configurable plain-English rules
- Job queue with all bucket statuses
- Duration tier logic and flags
- PM capacity settings and fluid capacity logic
- Geographic clustering with Google Maps API drive time
- Map view with job pins and cluster highlighting
- Must-Build protocol
- Not Built workflow with reason selection
- Stage 1 free weather API integration
- Basic settings panel

## **Phase 2 - JobNimbus Integration**

Target: Eliminate double entry, automate job intake.

- JN API read integration - jobs auto-populate from Schedule Job status
- JN note scanning for duration hints and permit status
- Note pushing back to JN for all decision scenarios
- Status monitoring - scheduler bucket updates based on JN status changes
- Webhook or polling for Job Complete status to auto-archive

## **Phase 3 - Weather Intelligence**

Target: Full two-stage weather system operational.

- BamWx API integration - final confirmation and night-before check
- Automated nightly BamWx run on all next-day builds
- Scheduler Decision workflow for marginal forecasts
- 5am morning-of free API spot check
- Material-specific threshold enforcement

## **Phase 4 - Intelligence Enhancements**

Target: Full live thinking machine operational.

- Dynamic rolling average sit time - auto-calculates from historical data
- Secondary trade aging alerts with configurable thresholds
- Rescheduled counter with customer communication flag after 2+ reschedules
- Standalone Rule - Saturday Build and Sales Rep Managed options fully integrated
- Full weekly plan view with drag-and-drop
- Scope change multi-day conversion workflow

# **12\. Technical Notes for Developer**

## **12.1 Recommended Stack**

The following stack is recommended based on the requirements - web-based, scalable from 20 to 200+ jobs, real-time updates, mobile-friendly browser access:

| **Frontend**        | React.js - component-based, good map library support, works well with real-time updates |
| ------------------- | --------------------------------------------------------------------------------------- |
| **Backend**         | Node.js or Python (FastAPI) - both have strong JobNimbus API and Anthropic SDK support  |
| **Database**        | PostgreSQL - job queue, scheduling history, settings, note logs                         |
| **AI Layer**        | Anthropic Claude API (claude-sonnet-4-6) - scoring engine and note generation           |
| **Maps**            | Google Maps API - geocoding, drive time calculation, map display                        |
| **Weather Stage 1** | OpenWeatherMap API or Weather.gov - free tier sufficient for daily polling              |
| **Weather Stage 2** | BamWx API - existing subscription, hyper-local construction forecasts                   |
| **Hosting**         | Any standard cloud provider (AWS, Render, Railway) - nothing exotic required            |

## **12.2 JobNimbus API Notes**

JobNimbus has an open REST API. The developer should review JN API documentation before beginning Phase 2. Key integration points:

- Authenticate via JN API key - stored securely as environment variable, never in code
- Poll for jobs at Schedule Job status on a regular interval OR use webhooks if JN supports them for status changes
- Map JN custom fields to scheduler data model - square footage, material type, trade types may be custom fields in the client's JN account
- Note creation endpoint - confirm character limits and formatting requirements
- Test in JN sandbox environment before writing to production job records

## **12.3 Court-Admissible Notes - Technical Requirements**

All notes pushed to JN by the system must meet the following technical standards:

- Always prefixed with \[SCHEDULER SYSTEM - date/time\] in a consistent, parseable format
- Never include subjective language, opinions about customers, or demographic references
- Geographic clustering logic must not use neighborhood names or demographic proxies - only driving distance and coordinates
- Timestamp must use the server clock, not the client browser clock
- All pushed notes are logged locally in the scheduler database with full audit trail
- Note templates are stored in settings and version-controlled - if a template changes, old notes reflect the template version at time of creation

## **12.4 AI Scoring Engine - Implementation Notes**

The AI scoring engine sends the following context to the Claude API on each scoring run:

- Full job queue data (all To Schedule jobs with all relevant fields)
- Available PM count and individual baselines
- Available crew count and specialty flags
- Current plain-English rules from settings panel
- Stage 1 weather data for the target date range
- Rolling average sit time
- Any Must-Build jobs with deadlines

The AI returns a structured recommendation (JSON) with job groupings, PM assignments, cluster rationale, and a human-readable explanation for each recommendation. The explanation is displayed to the scheduler in the UI.

Important: The AI layer should have a fallback. If the API call fails or times out, the system should surface a simple score-sorted list based on the weighted factors rather than returning an error. The scheduler should always have something actionable.

## **12.5 Data the Developer Needs from Client Before Build**

Before Phase 1 development begins, the developer should confirm the following with Indy Roof & Restoration:

- JobNimbus API key and sandbox access credentials
- Confirmation of which JN fields map to: material type, square footage, trade types, payment type
- Current PM roster and names for initial settings configuration
- Current crew roster and specialty capabilities
- BamWx API credentials and documentation
- Confirmation of material weather thresholds for each material type
- Any existing square footage data format in JN (squares vs square feet - confirm which unit)
- Confirmation of service area boundaries for map default viewport

**_End of Specification Document_**

Indy Roof & Restoration | Scheduling Intelligence System | Version 1.0 | March 2026