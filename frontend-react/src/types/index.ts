// Enums matching backend
export type JobBucket =
  | 'pending_confirmation'
  | 'coming_soon'
  | 'to_schedule'
  | 'scheduled'
  | 'not_built'
  | 'primary_complete'
  | 'waiting_on_trades'
  | 'review_for_completion'
  | 'completed';

export type PaymentType = 'cash' | 'finance' | 'insurance';
export type JobType = 'insurance' | 'retail';
export type DurationTier = 'tier_1' | 'tier_2' | 'tier_3' | 'low_slope';
export type MaterialType =
  | 'asphalt' | 'polymer_modified' | 'tpo' | 'duro_last'
  | 'epdm' | 'coating' | 'wood_shake' | 'slate'
  | 'metal' | 'siding' | 'other';
export type TradeType = 'roofing' | 'siding' | 'gutters' | 'windows' | 'paint' | 'interior' | 'other';
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
  primary_complete: 'Primary Complete',
  waiting_on_trades: 'Waiting on Trades',
  review_for_completion: 'Review for Completion',
  completed: 'Completed',
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
  siding: 'Siding',
  other: 'Other',
};

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
  created_at: string;
  updated_at: string;
}

export interface JobUpdate {
  must_build?: boolean;
  must_build_deadline?: string;
  must_build_reason?: string;
  bucket?: JobBucket;
  not_built_reason?: string;
  assigned_pm_id?: number;
  assigned_crew_id?: number;
  date_scheduled?: string;
  duration_days?: number;
  duration_confirmed?: boolean;
  standalone_option?: StandaloneOption;
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
  specialties: string[];
  is_active: boolean;
  created_at: string;
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
  customer_name?: string;
  address?: string;
  material_type?: string;
  payment_type?: string;
  must_build?: boolean;
  duration_days?: number;
  duration_confirmed?: boolean;
}

export interface WeatherBlockedJob {
  job_id: number;
  customer_name: string;
  address: string;
  material_type: MaterialType | null;
  weather_status: 'do_not_build';
  weather_detail: string;
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
}

export interface SystemSetting {
  value: string;
  description: string;
}

export type SettingsMap = Record<string, SystemSetting>;
