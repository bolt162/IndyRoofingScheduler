import {
  RefreshCw, Zap, ClipboardList,
  Package, CheckCircle2, Clock, Eye, Truck, User, MapPin,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { JobList } from '@/components/jobs/JobList';
import { JobCard } from '@/components/jobs/JobCard';
import { useState } from 'react';
import { useJobs, useBucketCounts, useSyncJN, useCreateJob, useUpdateJob } from '@/api/jobs';
import { Download, Plus } from 'lucide-react';
import { useRunScoring } from '@/api/scoring';
import { useCheckAllWeather } from '@/api/weather';
import { usePMs } from '@/api/settings';
import { useUIStore } from '@/stores/ui-store';
import { JobFormDialog } from '@/components/jobs/JobFormDialog';
import type { JobBucket } from '@/types';

const bucketCards = [
  { key: 'to_schedule' as JobBucket, label: 'To Schedule', icon: ClipboardList, color: 'text-blue-600' },
  { key: 'scheduled' as JobBucket, label: 'Scheduled', icon: CheckCircle2, color: 'text-green-600' },
  { key: 'primary_complete' as JobBucket, label: 'Primary Complete', icon: Package, color: 'text-purple-600' },
  { key: 'waiting_on_trades' as JobBucket, label: 'Waiting on Trades', icon: Clock, color: 'text-yellow-600' },
  { key: 'review_for_completion' as JobBucket, label: 'Review', icon: Eye, color: 'text-orange-600' },
  { key: 'completed' as JobBucket, label: 'Completed', icon: Truck, color: 'text-emerald-600' },
];

export function DashboardPage() {
  const { activeBucket, setActiveBucket, latestScoringResult: scoringResult, setLatestScoringResult } = useUIStore();
  const { data: counts, isLoading: countsLoading } = useBucketCounts();
  const { data: jobs, isLoading: jobsLoading } = useJobs(
    activeBucket === 'all' ? undefined : activeBucket
  );
  // Separate query for all jobs — used to compute secondary trade aging alerts
  const { data: allJobsForAging } = useJobs();

  const runScoring = useRunScoring();
  const checkWeather = useCheckAllWeather();
  const syncJN = useSyncJN();
  const createJob = useCreateJob();
  const { data: pms } = usePMs();
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const mustBuildJobs = jobs?.filter((j) => j.must_build) ?? [];

  const handleSyncJN = async () => {
    try {
      const result = await syncJN.mutateAsync();
      const scanMsg = result.scanned ? `, ${result.scanned} AI-scanned` : '';
      toast.success(`Synced: ${result.created} new, ${result.updated} updated from JN${scanMsg}`);
    } catch {
      toast.error('JN sync failed');
    }
  };

  const handleRunScoring = async () => {
    // Check if PMs exist before scoring
    if (!pms || pms.filter(p => p.is_active).length === 0) {
      toast.error('No PMs configured. Please add Project Managers in Settings → PM Roster before running scoring.');
      return;
    }
    try {
      const result = await runScoring.mutateAsync({});
      setLatestScoringResult(result);
      const blockedCount = result.weather_blocked_count ?? 0;
      const msg = blockedCount > 0
        ? `Scored ${result.recommendations.length} jobs (${blockedCount} blocked by weather)`
        : `Scored ${result.recommendations.length} jobs`;
      toast.success(msg);
    } catch {
      toast.error('Scoring failed');
    }
  };

  const [weatherAlerts, setWeatherAlerts] = useState<{
    rolled_back: { job_id: number; customer_name: string; detail: string }[];
    scheduler_decision: { job_id: number; customer_name: string; detail: string }[];
  } | null>(null);

  const handleCheckWeather = async () => {
    try {
      const result = await checkWeather.mutateAsync();
      const rb = result.rolled_back || [];
      const sd = result.scheduler_decision || [];
      setWeatherAlerts(rb.length > 0 || sd.length > 0 ? { rolled_back: rb, scheduler_decision: sd } : null);
      if (rb.length > 0) {
        toast.warning(`${rb.length} job(s) auto-removed due to weather`);
      } else if (sd.length > 0) {
        toast.info(`${sd.length} job(s) need scheduler weather decision`);
      } else {
        toast.success(`Weather check complete — ${result.total_checked} jobs checked, all clear`);
      }
    } catch {
      toast.error('Weather check failed');
    }
  };

  return (
    <div className="flex flex-col gap-4 md:gap-6 p-3 md:p-6">
      {/* Header with actions */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-xs md:text-sm text-muted-foreground">
            Job scheduling overview and AI tools
          </p>
        </div>
        <div className="grid grid-cols-2 md:flex md:items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowCreateDialog(true)}
            className="justify-center"
          >
            <Plus className="h-4 w-4 md:mr-1.5" />
            <span className="ml-1.5 md:ml-0">Create Job</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleSyncJN}
            disabled={syncJN.isPending}
            className="justify-center"
          >
            <Download className={`h-4 w-4 md:mr-1.5 ${syncJN.isPending ? 'animate-pulse' : ''}`} />
            <span className="ml-1.5 md:ml-0">{syncJN.isPending ? 'Syncing...' : 'Sync JN'}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheckWeather}
            disabled={checkWeather.isPending}
            className="justify-center"
          >
            <RefreshCw className={`h-4 w-4 md:mr-1.5 ${checkWeather.isPending ? 'animate-spin' : ''}`} />
            <span className="ml-1.5 md:ml-0">Check Weather</span>
          </Button>
          <Button
            size="sm"
            onClick={handleRunScoring}
            disabled={runScoring.isPending}
            className="justify-center"
          >
            <Zap className="h-4 w-4 md:mr-1.5" />
            <span className="ml-1.5 md:ml-0">{runScoring.isPending ? 'Scoring...' : 'Run Scoring'}</span>
          </Button>
        </div>
      </div>

      {/* Weather alert banners */}
      {weatherAlerts && weatherAlerts.rolled_back.length > 0 && (
        <Card className="border-red-300 bg-red-50">
          <CardContent className="p-4">
            <p className="text-sm font-semibold text-red-800 mb-1">
              {weatherAlerts.rolled_back.length} job(s) auto-removed due to weather
            </p>
            <ul className="text-xs text-red-700 space-y-0.5">
              {weatherAlerts.rolled_back.map(j => (
                <li key={j.job_id}>{j.customer_name} — {j.detail}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
      {weatherAlerts && weatherAlerts.scheduler_decision.length > 0 && (
        <Card className="border-yellow-300 bg-yellow-50">
          <CardContent className="p-4">
            <p className="text-sm font-semibold text-yellow-800 mb-1">
              {weatherAlerts.scheduler_decision.length} job(s) need weather decision
            </p>
            <p className="text-xs text-yellow-700">
              Click the yellow weather badge on each job card to include or exclude.
            </p>
            <ul className="text-xs text-yellow-700 space-y-0.5 mt-1">
              {weatherAlerts.scheduler_decision.map(j => (
                <li key={j.job_id}>{j.customer_name} — {j.detail}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Secondary trade escalation banners */}
      {(() => {
        if (!allJobsForAging) return null;
        const escalated = allJobsForAging.filter(j => j.secondary_aging_level === 'escalated');
        const warnings = allJobsForAging.filter(j => j.secondary_aging_level === 'warning');
        return (
          <>
            {escalated.length > 0 && (
              <Card className="border-red-400 bg-red-50">
                <CardContent className="p-4">
                  <p className="text-sm font-semibold text-red-800 mb-1">
                    🚨 {escalated.length} job(s) ESCALATED — secondary trades 10+ days overdue
                  </p>
                  <p className="text-xs text-red-700 mb-2">
                    Revenue is floating. Take immediate scheduling action.
                  </p>
                  <ul className="text-xs text-red-700 space-y-0.5">
                    {escalated.map(j => (
                      <li key={j.id}>
                        <button
                          className="underline hover:text-red-900"
                          onClick={() => setActiveBucket(j.bucket)}
                        >
                          {j.customer_name}
                        </button>
                        {' — '}{j.days_since_primary_complete}d since primary ·
                        {' '}open: {j.open_secondary_trades.join(', ') || '—'}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
            {warnings.length > 0 && (
              <Card className="border-yellow-400 bg-yellow-50">
                <CardContent className="p-4">
                  <p className="text-sm font-semibold text-yellow-800 mb-1">
                    ⚠ {warnings.length} job(s) overdue — secondary trades 7-9 days past primary
                  </p>
                  <ul className="text-xs text-yellow-800 space-y-0.5">
                    {warnings.map(j => (
                      <li key={j.id}>
                        <button
                          className="underline hover:text-yellow-900"
                          onClick={() => setActiveBucket(j.bucket)}
                        >
                          {j.customer_name}
                        </button>
                        {' — '}{j.days_since_primary_complete}d ·
                        {' '}open: {j.open_secondary_trades.join(', ') || '—'}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </>
        );
      })()}

      {/* Bucket summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 md:gap-3">
        {bucketCards.map(({ key, label, icon: Icon, color }) => (
          <Card
            key={key}
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setActiveBucket(key)}
          >
            <CardContent className="p-3 md:p-4">
              <div className="flex items-center justify-between">
                <Icon className={`h-4 w-4 md:h-5 md:w-5 ${color}`} />
                <span className="text-xl md:text-2xl font-bold tabular-nums">
                  {countsLoading ? '—' : (counts?.[key] ?? 0)}
                </span>
              </div>
              <p className="text-[10px] md:text-xs text-muted-foreground mt-1">{label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Must-Build highlight */}
      {mustBuildJobs.length > 0 && (
        <Card className="border-red-200 bg-red-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-red-700 flex items-center gap-2">
              🚨 Must-Build Jobs ({mustBuildJobs.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {mustBuildJobs.map((j) => (
                <JobCard key={j.id} job={j} compact />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Scoring result */}
      {scoringResult && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Zap className="h-4 w-4" />
              AI Scoring Explanation
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs whitespace-pre-wrap bg-muted p-3 rounded-md max-h-48 overflow-auto">
              {scoringResult.ai_explanation}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Weather-blocked jobs (spec 3.2: incompatible jobs filtered before scoring) */}
      {scoringResult?.weather_blocked && scoringResult.weather_blocked.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-amber-700 flex items-center gap-2">
              ⛅ Weather-Blocked Jobs ({scoringResult.weather_blocked.length})
              <span className="text-xs font-normal text-amber-600">
                — excluded from scoring due to incompatible forecast
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {scoringResult.weather_blocked.map((bj) => (
                <div
                  key={bj.job_id}
                  className="flex items-center justify-between text-xs bg-white rounded px-3 py-2 border border-amber-100"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-medium truncate">{bj.customer_name}</span>
                    <span className="text-muted-foreground truncate">{bj.address}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="outline" className="text-[10px] bg-red-50 text-red-700">
                      {bj.material_type ?? 'unknown'}
                    </Badge>
                    <span className="text-[10px] text-red-600 max-w-[200px] truncate" title={bj.weather_detail}>
                      {bj.weather_detail}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* PM Plan — grouped by PM with cluster info (spec 3.4) */}
      {scoringResult?.pm_plan && scoringResult.pm_plan.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <User className="h-4 w-4" />
            Recommended Build Plan by PM
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {scoringResult.pm_plan.map((pm) => (
              <Card
                key={pm.pm_id}
                className={
                  pm.over_max
                    ? 'border-red-300 bg-red-50/30'
                    : pm.over_baseline
                      ? 'border-yellow-300 bg-yellow-50/30'
                      : ''
                }
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <User className="h-4 w-4" />
                      {pm.pm_name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {pm.assigned_jobs}/{pm.baseline_capacity} jobs
                      </span>
                      <Badge
                        variant="outline"
                        className={`text-[10px] ${
                          pm.over_max
                            ? 'bg-red-100 text-red-800'
                            : pm.over_baseline
                              ? 'bg-yellow-100 text-yellow-800'
                              : 'bg-green-100 text-green-800'
                        }`}
                      >
                        {Math.round(pm.utilization * 100)}%
                      </Badge>
                    </div>
                  </div>
                  {/* Capacity bar */}
                  <div className="h-2 bg-muted rounded-full overflow-hidden mt-1">
                    <div
                      className={`h-full rounded-full transition-all ${
                        pm.over_max
                          ? 'bg-red-500'
                          : pm.over_baseline
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(pm.utilization * 100, 100)}%` }}
                    />
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  {/* Jobs grouped by cluster */}
                  {(() => {
                    const pmClusterIds = [...new Set(pm.jobs.map((j) => j.cluster_id).filter(Boolean))];
                    const standaloneJobs = pm.jobs.filter((j) => {
                      const cl = scoringResult.clusters?.find((c) => c.cluster_id === j.cluster_id);
                      return !cl || cl.is_standalone;
                    });
                    const clusteredGroups = pmClusterIds
                      .map((cid) => {
                        const cluster = scoringResult.clusters?.find((c) => c.cluster_id === cid);
                        if (!cluster || cluster.is_standalone) return null;
                        const jobs = pm.jobs.filter((j) => j.cluster_id === cid);
                        return { cluster, jobs };
                      })
                      .filter(Boolean) as Array<{ cluster: any; jobs: typeof pm.jobs }>;

                    return (
                      <div className="space-y-2">
                        {clusteredGroups.map(({ cluster, jobs }) => {
                          const distObjs = cluster.distances as Array<{ from: number; to: number; miles: number }> | undefined;
                          const maxDist = distObjs?.length ? Math.max(...distObjs.map((d: any) => d.miles)) : null;
                          return (
                            <div key={cluster.cluster_id}>
                              <div className={`text-[10px] px-2 py-1 rounded mb-1 ${
                                cluster.tier === 'tight'
                                  ? 'bg-green-50 text-green-700'
                                  : cluster.tier === 'close'
                                    ? 'bg-blue-50 text-blue-700'
                                    : 'bg-gray-50 text-gray-700'
                              }`}>
                                <MapPin className="h-3 w-3 inline mr-1" />
                                {jobs.length} jobs · {cluster.tier} cluster
                                {maxDist !== null && ` · within ${maxDist.toFixed(1)} mi`}
                              </div>
                              {jobs.map((j) => (
                                <div
                                  key={j.job_id}
                                  className="flex items-center justify-between text-xs bg-white rounded px-3 py-1.5 border ml-3"
                                >
                                  <div className="flex items-center gap-2 min-w-0">
                                    <span className="font-mono text-[10px] text-muted-foreground w-8">
                                      {j.score?.toFixed(0)}
                                    </span>
                                    <span className="font-medium truncate">{j.customer_name}</span>
                                    {j.suggested_crew_name && (
                                      <Badge
                                        variant="outline"
                                        className={
                                          j.suggested_crew_rank === 1
                                            ? 'text-[9px] bg-yellow-50 text-yellow-800 border-yellow-400 font-bold shrink-0'
                                            : j.suggested_crew_rank && j.suggested_crew_rank <= 3
                                            ? 'text-[9px] bg-indigo-50 text-indigo-700 border-indigo-300 shrink-0'
                                            : 'text-[9px] shrink-0'
                                        }
                                        title={j.complexity_score != null ? `Complexity ${j.complexity_score.toFixed(0)}` : undefined}
                                      >
                                        👷 {j.suggested_crew_name}{j.suggested_crew_rank && j.suggested_crew_rank < 999 ? ` #${j.suggested_crew_rank}` : ''}
                                      </Badge>
                                    )}
                                    {!j.suggested_crew_name && j.crew_warning && (
                                      <Badge variant="outline" className="text-[9px] bg-red-50 text-red-700 border-red-300 shrink-0" title={j.crew_warning}>
                                        ⚠ {j.crew_warning.length > 30 ? 'No crew' : j.crew_warning}
                                      </Badge>
                                    )}
                                  </div>
                                  {j.must_build && (
                                    <Badge variant="outline" className="text-[9px] bg-red-100 text-red-800 shrink-0">Must-Build</Badge>
                                  )}
                                </div>
                              ))}
                            </div>
                          );
                        })}

                        {standaloneJobs.length > 0 && (
                          <div>
                            <div className="text-[10px] px-2 py-1 rounded mb-1 bg-amber-50 text-amber-700">
                              <MapPin className="h-3 w-3 inline mr-1" />
                              {standaloneJobs.length} standalone job{standaloneJobs.length > 1 ? 's' : ''}
                            </div>
                            {standaloneJobs.map((j) => (
                              <div
                                key={j.job_id}
                                className="flex items-center justify-between text-xs bg-white rounded px-3 py-1.5 border ml-3 border-amber-200"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="font-mono text-[10px] text-muted-foreground w-8">
                                    {j.score?.toFixed(0)}
                                  </span>
                                  <span className="font-medium truncate">{j.customer_name}</span>
                                  {j.suggested_crew_name && (
                                    <Badge
                                      variant="outline"
                                      className={
                                        j.suggested_crew_rank === 1
                                          ? 'text-[9px] bg-yellow-50 text-yellow-800 border-yellow-400 font-bold shrink-0'
                                          : j.suggested_crew_rank && j.suggested_crew_rank <= 3
                                          ? 'text-[9px] bg-indigo-50 text-indigo-700 border-indigo-300 shrink-0'
                                          : 'text-[9px] shrink-0'
                                      }
                                      title={j.complexity_score != null ? `Complexity ${j.complexity_score.toFixed(0)}` : undefined}
                                    >
                                      👷 {j.suggested_crew_name}{j.suggested_crew_rank && j.suggested_crew_rank < 999 ? ` #${j.suggested_crew_rank}` : ''}
                                    </Badge>
                                  )}
                                  {!j.suggested_crew_name && j.crew_warning && (
                                    <Badge variant="outline" className="text-[9px] bg-red-50 text-red-700 border-red-300 shrink-0" title={j.crew_warning}>
                                      ⚠ {j.crew_warning.length > 30 ? 'No crew' : j.crew_warning}
                                    </Badge>
                                  )}
                                </div>
                                {j.must_build && (
                                  <Badge variant="outline" className="text-[9px] bg-red-100 text-red-800 shrink-0">Must-Build</Badge>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        {pm.assigned_jobs === 0 && (
                          <p className="text-xs text-muted-foreground italic py-2">No jobs assigned</p>
                        )}
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Unassigned overflow */}
          {scoringResult.unassigned_jobs && scoringResult.unassigned_jobs.length > 0 && (
            <Card className="border-dashed">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">
                  Unassigned Jobs ({scoringResult.unassigned_jobs.length})
                  <span className="text-xs font-normal ml-2">
                    — exceeded PM capacity, needs manual assignment
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {scoringResult.unassigned_jobs.map((j) => (
                    <div key={j.job_id} className="text-xs flex items-center gap-2">
                      <span className="font-mono text-muted-foreground w-8">{j.score?.toFixed(0)}</span>
                      <span>{j.customer_name}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <Separator />

      {/* Job Queue with bucket tabs */}
      <div>
        <Tabs
          value={activeBucket}
          onValueChange={(v) => setActiveBucket(v as JobBucket | 'all')}
        >
          <div className="overflow-x-auto mb-3 -mx-1 px-1">
            <TabsList className="w-max">
              <TabsTrigger value="all">
                All
                {counts && (
                  <Badge variant="secondary" className="ml-1.5 text-[10px]">
                    {Object.values(counts).reduce((a, b) => a + b, 0)}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="to_schedule">To Schedule</TabsTrigger>
              <TabsTrigger value="scheduled">Scheduled</TabsTrigger>
              <TabsTrigger value="primary_complete">Primary Complete</TabsTrigger>
              <TabsTrigger value="waiting_on_trades">Waiting Trades</TabsTrigger>
              <TabsTrigger value="review_for_completion">Review</TabsTrigger>
            </TabsList>
          </div>
        </Tabs>

        {jobsLoading ? (
          <div className="text-sm text-muted-foreground py-8 text-center">Loading jobs...</div>
        ) : (
          <JobList jobs={jobs ?? []} />
        )}
      </div>

      {/* Create Job Dialog */}
      <JobFormDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        mode="create"
        onSubmit={async (data) => {
          try {
            await createJob.mutateAsync(data as any);
            toast.success('Job created successfully');
            setShowCreateDialog(false);
          } catch {
            toast.error('Failed to create job');
          }
        }}
        isPending={createJob.isPending}
      />
    </div>
  );
}
