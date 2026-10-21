// Enums matching backend
export type JobBucket =
  | 'pending_confirmation'
  | 'coming_soon'
  | 'to_schedule'
  | 'scheduled'
  | 'not_built'
  | 'other_trades'
  | 'primary_completed'
  | 'completed'
  | 'archived';

export type PaymentType = 'cash' | 'finance' | 'insurance';
export type JobType = 'insurance' | 'retail';
export type DurationTier = 'tier_1' | 'tier_2' | 'tier_3' | 'low_slope';
// NOTE: 'siding' is intentionally NOT a material type — it's a trade.
// Siding-only jobs have material_type='' and primary_trade='siding'.
// Weather thresholds for siding jobs are applied via primary_trade in backend.
export type MaterialType =
  | 'asphalt' | 'polymer_modified' | 'tpo' | 'duro_last'
  | 'epdm' | 'coating' | 'wood_shake' | 'slate'
  | 'metal' | 'other';
export type TradeType =
  | 'roofing' | 'roofing_repair' | 'siding' | 'siding_repair'
  | 'gutters' | 'windows' | 'paint' | 'interior' | 'other';
export type WeatherStatus = 'clear' | 'do_not_build' | 'scheduler_decision';
export type PlanStatus = 'draft' | 'confirmed' | 'cancelled';
export type NoteType =
  | 'scheduling_decision' | 'not_built' | 'secondary_trade_alert'
  | 'weather_rollback' | 'standalone_rule' | 'night_before_weather';
export type StandaloneOption = 'saturday_build' | 'sales_rep_managed';

export const NOT_BUILT_REASONS = [
  'Weather Pre-Build',
  'Weather Mid-Build',
  'Scope Change',
  'Crew Unavailable',
  'Material Issue',
  'Customer Related',
  'Other',
] as const;

export const BUCKET_LABELS: Record<JobBucket, string> = {
  pending_confirmation: 'Pending Confirmation',
  coming_soon: 'Coming Soon',
  to_schedule: 'To Schedule',
  scheduled: 'Scheduled',
  not_built: 'Not Built',
  other_trades: 'Other Trades',
  primary_completed: 'Primary Completed',
  completed: 'Completed',
  archived: 'Archived',
};

export const MATERIAL_LABELS: Record<MaterialType, string> = {
  asphalt: 'Asphalt',
  polymer_modified: 'Polymer Modified',
  tpo: 'TPO',
  duro_last: 'Duro-Last',
  epdm: 'EPDM',
  coating: 'Coating',
  wood_shake: 'Wood Shake',
  slate: 'Slate',
  metal: 'Metal',
  other: 'Other',
};

// A date range the customer asked us not to build (ISO yyyy-MM-dd, both ends inclusive)
export interface NoBuildWindow {
  start: string;
  end: string;
  reason: string | null;
}

// Main data types
export interface Job {
  id: number;
  jn_job_id: string | null;
  customer_name: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  job_type: JobType | null;
  payment_type: PaymentType | null;
  primary_trade: TradeType | null;
  secondary_trades: string[] | null;
  material_type: MaterialType | null;
  square_footage: number | null;
  date_entered: string | null;
  date_scheduled: string | null;
  sales_rep: string | null;
  assigned_pm_id: number | null;
  assigned_crew_id: number | null;
  duration_days: number;
  duration_confirmed: boolean;
  duration_tier: DurationTier | null;
  duration_source: string | null;
  permit_confirmed: boolean;
  must_build: boolean;
  must_build_deadline: string | null;
  must_build_reason: string | null;
  crew_requirement_flag: boolean;
  crew_requirement_note: string | null;
  standalone_rule: boolean;
  standalone_option: StandaloneOption | null;
  // Only windows that haven't ended yet
  no_build_dates: NoBuildWindow[];
  bucket: JobBucket;
  rescheduled_count: number;
  not_built_reason: string | null;
  priority_bump: number;
  is_multi_day: boolean;
  multi_day_current: number;
  score: number;
  score_explanation: string | null;
  jn_status: string | null;
  jn_notes_raw: string | null;
  ai_note_scan_result: string | null;
  weather_status: WeatherStatus | null;
  weather_detail: string | null;
  primary_complete_date: string | null;
  secondary_trades_status: Record<string, string> | null;
  latest_system_note: string | null;
  latest_system_note_id: number | null;
  latest_system_note_pushed: boolean | null;
  latest_system_note_pushed_at: string | null;
  // Secondary trade aging (post primary-complete tracking)
  days_since_primary_complete: number | null;
  secondary_aging_level: 'normal' | 'warning' | 'escalated' | null;
  open_secondary_trades: string[];
  created_at: string;
  updated_at: string;
  // Stamp of last AI re-analysis (note scan + recompute). If older than updated_at,
  // the job has changes that haven't been fed to the AI yet.
  last_ai_analyzed_at: string | null;
  // What JobNimbus has on the calendar (read every sync)
  jn_start_date: string | null;
  jn_crews: string[] | null;
  jn_pm: string | null;
  jn_work_orders: JNWorkOrder[] | null;
  // Day picked on the Weekly Plan, not sent to JobNimbus yet
  planned_date: string | null;
  planned_pm_id: number | null;
  planned_crew_id: number | null;
  // Build days picked on the card; else days_suggestion (from the work order) is booked
  planned_days: number | null;
  days_suggestion: { days: number; why: string } | null;
  // Crew notes: suggested lines, and the ones a scheduler approved for the work order
  crew_note_suggestions: CrewNoteSuggestion[] | null;
  crew_notes_approved: string[] | null;
  crew_notes_by: string | null;
  crew_notes_at: string | null;
  // Push to JobNimbus: one key per finished step, plus why it last stopped
  jn_push_steps: Record<string, unknown> | null;
  jn_push_error: string | null;
  planned_by: string | null;
  planned_at: string | null;
  // "Suggest builds": pencilled in, not a plan until someone keeps it
  suggested_date: string | null;
  suggested_crew_id: number | null;
  suggested_pm_id: number | null;
  suggested_days: number | null;
  suggested_why: string | null;
  // Notes ready check
  ready_status: ReadyStatus | null;
  ready_flags: ReadyFlag[] | null;
  ready_checked_at: string | null;
  ready_decision_by: string | null;
  ready_decision_at: string | null;
  ready_decision_note: string | null;
}

export interface JNWorkOrder {
  number: string;
  trade: string;
  status: string;
  start: string | null;
  crews: string[];
  pm: string | null;
  internal_note: string;
  customer_note: string;
}

// clear: nothing holds it up · flagged: needs an answer · ok: office said fine · hold: wait
export type ReadyStatus = 'clear' | 'flagged' | 'ok' | 'hold';

export interface ReadyFlag {
  issue: string;
  quote: string;
  source: string;
}

export interface JobNote {
  id: number;
  note_type: NoteType;
  note_text: string;
  pushed_to_jn: boolean;
  pushed_at: string | null;
  jn_note_id: string | null;
  push_error: string | null;
  created_at: string;
}

export interface JobCreate {
  customer_name: string;
  address: string;
  job_type?: string;
  payment_type: string;
  primary_trade?: string;
  secondary_trades?: string[];
  material_type: string;
  square_footage?: number | null;
  sales_rep?: string | null;
  duration_days?: number;
  notes?: string | null;
}

export interface JobUpdate {
  must_build?: boolean;
  must_build_deadline?: string;
  must_build_reason?: string;
  bucket?: JobBucket;
  not_built_reason?: string;
  // Nullable so a job can be unscheduled (cleared back to the unassigned queue)
  assigned_pm_id?: number | null;
  assigned_crew_id?: number | null;
  date_scheduled?: string | null;
  duration_days?: number;
  duration_confirmed?: boolean;
  standalone_option?: StandaloneOption;
  // Editable job details
  customer_name?: string;
  address?: string;
  job_type?: string;
  payment_type?: string;
  primary_trade?: string;
  secondary_trades?: string[];
  material_type?: string;
  square_footage?: number | null;
  sales_rep?: string | null;
  notes?: string | null;
  permit_confirmed?: boolean;
  crew_requirement_flag?: boolean;
  // Scheduler confirmed it's OK to build inside the job's No-Build Dates
  override_no_build?: boolean;
  // Weekly Plan pick; null clears the plan
  planned_date?: string | null;
  planned_pm_id?: number | null;
  planned_crew_id?: number | null;
  planned_days?: number | null;
}

export interface NotBuiltRequest {
  reason: string;
  detail?: string;
}

export interface PM {
  id: number;
  name: string;
  baseline_capacity: number;
  max_capacity: number;
  is_active: boolean;
  created_at: string;
}

export interface Crew {
  id: number;
  name: string;
  // Trades this crew works on: e.g., ["roofing"], ["siding"], or ["roofing", "siding"]
  // Used for trade-aware crew matching — a roofing-only crew is never assigned to a siding job
  trades: string[];
  // Material specialties: slate, tpo, wood_shake, etc. (optional)
  specialties: string[];
  is_active: boolean;
  rank: number; // 1 = best ("Michael Jordan"), higher = bench. 999 = unranked
  notes: string | null;
  // The crew's subcontractor name in JobNimbus, for Push to JobNimbus
  jn_name: string | null;
  created_at: string;
}

export interface CrewNoteSuggestion {
  text: string;
  quote?: string;
  source?: string;
  kind: 'gutters' | 'notes';
}

export interface PushPreviewItem {
  job_id: number;
  customer_name: string;
  planned_date: string;
  crew: string | null;
  pm: string | null;
  days: number;
  crew_notes: number | null;
  crew_notes_waiting: boolean;
  ready: boolean;
  reason: string | null;
}

export interface PushPreview {
  mode: 'off' | 'test' | 'live';
  items: PushPreviewItem[];
  ready_count: number;
  can_book: boolean;
}

export interface PushResult {
  job_id: number;
  customer_name: string;
  status: 'booked' | 'skipped' | 'failed';
  reason?: string;
  work_order?: string;
  jn_error?: boolean;
}

export interface NoteLog {
  id: number;
  job_id: number;
  jn_job_id: string | null;
  note_type: NoteType;
  note_text: string;
  pushed_to_jn: boolean;
  template_version: number;
  created_at: string;
}

export interface SchedulePlan {
  id: number;
  plan_date: string;
  pm_id: number | null;
  job_ids: number[];
  cluster_info: Record<string, unknown> | null;
  status: PlanStatus;
  weather_status: string | null;
  ai_explanation: string | null;
  created_at: string;
  updated_at: string;
}

export interface BucketCounts {
  [key: string]: number;
}

export interface ScoringResult {
  job_id: number;
  score: number;
  explanation: string;
  cluster_id: string | null;
  suggested_pm_id?: number | null;
  // Crew recommendation (from crew_matching service)
  suggested_crew_id?: number | null;
  suggested_crew_name?: string | null;
  suggested_crew_rank?: number | null;
  complexity_score?: number | null;
  crew_warning?: string | null;
  customer_name?: string;
  address?: string;
  material_type?: string;
  payment_type?: string;
  must_build?: boolean;
  duration_days?: number;
  duration_confirmed?: boolean;
  no_build_dates?: NoBuildWindow[];
}

export interface WeatherBlockedJob {
  job_id: number;
  customer_name: string;
  address: string;
  material_type: MaterialType | null;
  weather_status: 'do_not_build';
  weather_detail: string;
}

export interface NoBuildBlockedJob {
  job_id: number;
  customer_name: string;
  address: string;
  must_build: boolean;
  must_build_deadline: string | null;
  no_build_start: string;
  no_build_end: string;
  no_build_reason: string | null;
  detail: string;
}

export interface ClusterDistance {
  from: number;
  to: number;
  miles: number;
}

export interface ClusterInfo {
  cluster_id: string;
  tier: 'tight' | 'close' | 'standard' | 'standalone';
  suggested_pm_capacity: number;
  assigned_pm_id: number | null;
  assigned_pm_name: string | null;
  job_ids: number[];
  total_score: number;
  is_standalone: boolean;
  has_must_build: boolean;
  distances?: ClusterDistance[];
}

export interface PMPlanEntry {
  pm_id: number;
  pm_name: string;
  baseline_capacity: number;
  max_capacity: number;
  assigned_jobs: number;
  clusters: string[];
  utilization: number;
  over_baseline: boolean;
  over_max: boolean;
  jobs: ScoringResult[];
}

export interface ScoringResponse {
  recommendations: ScoringResult[];
  clusters: ClusterInfo[];
  pm_plan?: PMPlanEntry[];
  unassigned_jobs?: ScoringResult[];
  ai_explanation: string;
  weather_blocked?: WeatherBlockedJob[];
  weather_blocked_count?: number;
  no_build_blocked?: NoBuildBlockedJob[];
  no_build_blocked_count?: number;
}

export interface SystemSetting {
  value: string;
  description: string;
}

export type SettingsMap = Record<string, SystemSetting>;
