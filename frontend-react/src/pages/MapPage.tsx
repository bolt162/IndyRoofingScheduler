import { useMemo, useState, useEffect, useRef } from 'react';
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
} from '@vis.gl/react-google-maps';
import { useJobs } from '@/api/jobs';
import { usePMs } from '@/api/settings';
import { useUIStore } from '@/stores/ui-store';
import { JobCard } from '@/components/jobs/JobCard';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Layers, Users, MapPin, ClipboardList } from 'lucide-react';
import type { Job, JobBucket, ClusterInfo, ScoringResult } from '@/types';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '';

// PM color palette
const PM_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
];

const CLUSTER_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
  '#14B8A6', '#F43F5E', '#A855F7', '#FB923C', '#22D3EE',
];

function getMarkerColor(
  job: Job,
  mapMode: 'status' | 'pm' | 'plan',
  pmIndex: globalThis.Map<number, number>,
  scoringPMMap: globalThis.Map<number, number>,
  // For plan mode: cluster-based coloring
  clusterColorMap?: globalThis.Map<string, string>,
  jobClusterMap?: globalThis.Map<number, string>,
) {
  if (job.must_build) return '#DC2626'; // red always

  if (mapMode === 'plan' && clusterColorMap && jobClusterMap) {
    const clusterId = jobClusterMap.get(job.id);
    if (clusterId) {
      return clusterColorMap.get(clusterId) || '#6B7280';
    }
    return '#6B7280'; // unassigned
  }

  if (mapMode === 'pm') {
    if (job.standalone_rule) return '#F59E0B';
    const pmId = scoringPMMap.get(job.id) ?? job.assigned_pm_id;
    if (pmId) {
      const idx = pmIndex.get(pmId) ?? 0;
      return PM_COLORS[idx % PM_COLORS.length];
    }
  }

  // Status mode (default)
  if (job.standalone_rule) return '#F59E0B';
  switch (job.bucket) {
    case 'scheduled': return '#22C55E';
    case 'to_schedule': return '#3B82F6';
    case 'primary_complete': return '#A855F7';
    default: return '#6B7280';
  }
}

function MarkerPin({ color, label, dimmed }: { color: string; label: string; dimmed?: boolean }) {
  return (
    <div className="flex flex-col items-center" style={{ opacity: dimmed ? 0.3 : 1 }}>
      <div
        className="w-6 h-6 rounded-full border-2 border-white shadow-md flex items-center justify-center text-[8px] font-bold text-white"
        style={{ backgroundColor: color }}
      >
        {label}
      </div>
      <div
        className="w-0 h-0 -mt-0.5"
        style={{
          borderLeft: '4px solid transparent',
          borderRight: '4px solid transparent',
          borderTop: `6px solid ${color}`,
        }}
      />
    </div>
  );
}

// Helper: compute max distance from cluster distances array
function getClusterMaxMiles(cluster: ClusterInfo): number {
  const dists = cluster.distances || [];
  if (dists.length === 0) return 0;
  return Math.max(...dists.map(d => d.miles));
}

// Build plan data structure: PM → Clusters → Jobs
interface PlanCluster {
  clusterId: string;
  clusterInfo: ClusterInfo;
  jobs: ScoringResult[];
  maxMiles: number;
  color: string;
}

interface PlanPM {
  pmId: number;
  pmName: string;
  clusters: PlanCluster[];
  standaloneJobs: ScoringResult[];
  totalJobs: number;
}

export function MapPage() {
  const { mapMode, setMapMode, latestScoringResult } = useUIStore();

  // On first mount, default to 'plan' if scoring results exist, otherwise 'status'
  const initialSet = useRef(false);
  useEffect(() => {
    if (!initialSet.current) {
      initialSet.current = true;
      if (latestScoringResult?.pm_plan && latestScoringResult.pm_plan.length > 0) {
        setMapMode('plan');
      } else if (mapMode === 'plan') {
        setMapMode('status');
      }
    }
  }, [latestScoringResult, mapMode, setMapMode]);
  const [bucketFilter, setBucketFilter] = useState<JobBucket | 'all'>('all');
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [selectedPMFilter, setSelectedPMFilter] = useState<number | null>(null);
  // Plan mode: selected cluster or PM for highlighting
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [selectedPlanPM, setSelectedPlanPM] = useState<number | null>(null);
  // Mobile view: 'map' or 'list' (below md — user toggles between full-width panes)
  const [mobileView, setMobileView] = useState<'map' | 'list'>('map');

  const { data: allJobs } = useJobs();
  const { data: pms } = usePMs();

  // Build PM index for color assignment
  const pmIndex = useMemo(() => {
    const m = new globalThis.Map<number, number>();
    pms?.forEach((pm, i) => m.set(pm.id, i));
    return m;
  }, [pms]);

  // Build job→PM lookup from latest scoring result
  const scoringPMMap = useMemo(() => {
    const m = new globalThis.Map<number, number>();
    if (latestScoringResult?.pm_plan) {
      for (const pm of latestScoringResult.pm_plan) {
        for (const job of pm.jobs) {
          m.set(job.job_id, pm.pm_id);
        }
      }
    }
    return m;
  }, [latestScoringResult]);

  // Build cluster data for plan mode
  const { planPMs, clusterColorMap, jobClusterMap, planJobIds } = useMemo(() => {
    const planPMs: PlanPM[] = [];
    const clusterColorMap = new globalThis.Map<string, string>();
    const jobClusterMap = new globalThis.Map<number, string>();
    const planJobIds = new Set<number>();
    let colorIdx = 0;

    if (latestScoringResult?.pm_plan && latestScoringResult?.clusters) {
      const clusterLookup = new globalThis.Map<string, ClusterInfo>();
      for (const c of latestScoringResult.clusters) {
        clusterLookup.set(c.cluster_id, c);
      }

      for (const pmPlan of latestScoringResult.pm_plan) {
        const pmClusters: PlanCluster[] = [];
        const standaloneJobs: ScoringResult[] = [];

        // Group jobs by cluster_id
        const jobsByCluster = new globalThis.Map<string, ScoringResult[]>();
        for (const job of pmPlan.jobs) {
          const cid = job.cluster_id || 'standalone';
          if (!jobsByCluster.has(cid)) jobsByCluster.set(cid, []);
          jobsByCluster.get(cid)!.push(job);
          planJobIds.add(job.job_id);
        }

        for (const [cid, jobs] of jobsByCluster.entries()) {
          const clusterInfo = clusterLookup.get(cid);
          if (cid === 'standalone' || !clusterInfo || clusterInfo.is_standalone) {
            standaloneJobs.push(...jobs);
            for (const j of jobs) {
              jobClusterMap.set(j.job_id, `standalone_${pmPlan.pm_id}`);
            }
          } else {
            const color = CLUSTER_COLORS[colorIdx % CLUSTER_COLORS.length];
            colorIdx++;
            clusterColorMap.set(cid, color);
            for (const j of jobs) {
              jobClusterMap.set(j.job_id, cid);
            }
            pmClusters.push({
              clusterId: cid,
              clusterInfo,
              jobs,
              maxMiles: getClusterMaxMiles(clusterInfo),
              color,
            });
          }
        }

        // Standalone gets amber
        const standaloneKey = `standalone_${pmPlan.pm_id}`;
        clusterColorMap.set(standaloneKey, '#F59E0B');

        planPMs.push({
          pmId: pmPlan.pm_id,
          pmName: pmPlan.pm_name,
          clusters: pmClusters,
          standaloneJobs,
          totalJobs: pmPlan.jobs.length,
        });
      }
    }

    return { planPMs, clusterColorMap, jobClusterMap, planJobIds };
  }, [latestScoringResult]);

  // Filter jobs with lat/lng
  const jobs = useMemo(() => {
    let result = allJobs?.filter((j) => j.latitude && j.longitude) ?? [];
    if (bucketFilter !== 'all') {
      result = result.filter((j) => j.bucket === bucketFilter);
    }
    if (mapMode === 'pm' && scoringPMMap.size > 0) {
      result = result.filter((j) => scoringPMMap.has(j.id) || j.assigned_pm_id);
      if (selectedPMFilter !== null) {
        result = result.filter(
          (j) => (scoringPMMap.get(j.id) ?? j.assigned_pm_id) === selectedPMFilter
        );
      }
    }
    if (mapMode === 'plan') {
      // Show only jobs that are in the build plan
      if (planJobIds.size > 0) {
        result = result.filter(j => planJobIds.has(j.id));
        // Further filter by selected PM in plan mode
        if (selectedPlanPM !== null) {
          const pmJobs = new Set<number>();
          const pm = planPMs.find(p => p.pmId === selectedPlanPM);
          if (pm) {
            for (const c of pm.clusters) for (const j of c.jobs) pmJobs.add(j.job_id);
            for (const j of pm.standaloneJobs) pmJobs.add(j.job_id);
          }
          result = result.filter(j => pmJobs.has(j.id));
        }
      }
    }
    return result;
  }, [allJobs, bucketFilter, mapMode, scoringPMMap, selectedPMFilter, planJobIds, selectedPlanPM, planPMs]);

  // Determine which jobs are "highlighted" (not dimmed)
  const highlightedJobIds = useMemo(() => {
    if (mapMode !== 'plan') return null; // no dimming in other modes
    if (!selectedClusterId && selectedPlanPM === null) return null; // no filter = all bright

    const ids = new Set<number>();
    if (selectedClusterId) {
      // Highlight only jobs in the selected cluster
      for (const pm of planPMs) {
        for (const c of pm.clusters) {
          if (c.clusterId === selectedClusterId) {
            for (const j of c.jobs) ids.add(j.job_id);
          }
        }
        if (selectedClusterId === `standalone_${pm.pmId}`) {
          for (const j of pm.standaloneJobs) ids.add(j.job_id);
        }
      }
    }
    return ids.size > 0 ? ids : null;
  }, [mapMode, selectedClusterId, selectedPlanPM, planPMs]);

  // Center on Indianapolis by default
  const center = useMemo(() => {
    if (jobs.length === 0) return { lat: 39.7684, lng: -86.1581 };
    const lat = jobs.reduce((s, j) => s + (j.latitude ?? 0), 0) / jobs.length;
    const lng = jobs.reduce((s, j) => s + (j.longitude ?? 0), 0) / jobs.length;
    return { lat, lng };
  }, [jobs]);

  return (
    <div className="flex flex-col md:flex-row h-full">
      {/* Mobile toggle bar — switches between list view and map view */}
      <div className="md:hidden flex border-b">
        <button
          type="button"
          className={`flex-1 py-2 text-xs font-medium border-b-2 transition-colors ${
            mobileView === 'map'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground'
          }`}
          onClick={() => setMobileView('map')}
        >
          Map
        </button>
        <button
          type="button"
          className={`flex-1 py-2 text-xs font-medium border-b-2 transition-colors ${
            mobileView === 'list'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground'
          }`}
          onClick={() => setMobileView('list')}
        >
          Jobs & Plan
        </button>
      </div>

      {/* Sidebar — full-width on mobile (hidden when map selected), 320px on desktop */}
      <div className={`${mobileView === 'list' ? 'flex' : 'hidden'} md:flex w-full md:w-80 md:border-r flex-col overflow-hidden`}>
        <div className="p-4 space-y-3 shrink-0">
          <h2 className="text-lg font-semibold">Map View</h2>

          {/* Mode buttons */}
          <div className="flex gap-1.5">
            <Button
              variant={mapMode === 'status' ? 'default' : 'outline'}
              size="sm"
              className="text-xs h-7"
              onClick={() => { setMapMode('status'); setSelectedPMFilter(null); setSelectedClusterId(null); setSelectedPlanPM(null); }}
            >
              <Layers className="h-3 w-3 mr-1" />
              Job Status
            </Button>
            <Button
              variant={mapMode === 'pm' ? 'default' : 'outline'}
              size="sm"
              className="text-xs h-7"
              onClick={() => { setMapMode('pm'); setSelectedClusterId(null); setSelectedPlanPM(null); }}
            >
              <Users className="h-3 w-3 mr-1" />
              PM
            </Button>
            <Button
              variant={mapMode === 'plan' ? 'default' : 'outline'}
              size="sm"
              className="text-xs h-7"
              onClick={() => { setMapMode('plan'); setSelectedPMFilter(null); }}
            >
              <ClipboardList className="h-3 w-3 mr-1" />
              Build Plan
            </Button>
          </div>

          {/* Bucket filter — only in status mode */}
          {mapMode === 'status' && (
            <Select
              value={bucketFilter}
              onValueChange={(v) => setBucketFilter(v as JobBucket | 'all')}
            >
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Filter bucket" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Buckets</SelectItem>
                <SelectItem value="to_schedule">To Schedule</SelectItem>
                <SelectItem value="scheduled">Scheduled</SelectItem>
                <SelectItem value="primary_complete">Primary Complete</SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>

        <Separator className="shrink-0" />

        {/* PM Legend — PM Assignments mode */}
        {mapMode === 'pm' && pms && (
          <div className="p-4 shrink-0">
            <p className="text-xs font-semibold text-muted-foreground mb-2">PM Legend</p>
            {scoringPMMap.size > 0 ? (
              <p className="text-[10px] text-blue-600 mb-2 italic">
                Click a PM to filter · click again to show all
              </p>
            ) : (
              <p className="text-[10px] text-amber-600 mb-2 italic">
                Run scoring on Dashboard to see PM assignments
              </p>
            )}
            <div className="space-y-1">
              {pms.filter((p) => p.is_active).map((pm, i) => {
                const pmPlan = latestScoringResult?.pm_plan?.find((p) => p.pm_id === pm.id);
                const isSelected = selectedPMFilter === pm.id;
                return (
                  <div
                    key={pm.id}
                    className={`flex items-center gap-2 text-xs cursor-pointer rounded px-1.5 py-0.5 transition-colors ${
                      isSelected ? 'bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-muted'
                    }`}
                    onClick={() => setSelectedPMFilter(isSelected ? null : pm.id)}
                  >
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ backgroundColor: PM_COLORS[i % PM_COLORS.length] }}
                    />
                    <span className="truncate">{pm.name}</span>
                    {pmPlan && (
                      <span className="text-[10px] text-muted-foreground ml-auto">
                        {pmPlan.assigned_jobs} jobs
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Build Plan Panel — plan mode */}
        {mapMode === 'plan' && (
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
            {planPMs.length === 0 ? (
              <div className="p-4 text-center">
                <p className="text-xs text-amber-600 italic">
                  Run Scoring on the Dashboard first to see the Build Plan
                </p>
              </div>
            ) : (
              <ScrollArea className="flex-1 min-h-0">
                <div className="p-3 space-y-3">
                  {/* Reset button */}
                  {(selectedClusterId || selectedPlanPM !== null) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full h-6 text-[10px] text-muted-foreground"
                      onClick={() => { setSelectedClusterId(null); setSelectedPlanPM(null); }}
                    >
                      Show All · Reset Filter
                    </Button>
                  )}

                  {planPMs.map((pm) => {
                    const pmIdx = pmIndex.get(pm.pmId) ?? 0;
                    const pmColor = PM_COLORS[pmIdx % PM_COLORS.length];
                    const isPMSelected = selectedPlanPM === pm.pmId;

                    return (
                      <div key={pm.pmId} className="space-y-1.5">
                        {/* PM Header */}
                        <div
                          className={`flex items-center gap-2 cursor-pointer rounded px-2 py-1.5 transition-colors ${
                            isPMSelected ? 'bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-muted'
                          }`}
                          onClick={() => {
                            setSelectedPlanPM(isPMSelected ? null : pm.pmId);
                            setSelectedClusterId(null);
                          }}
                        >
                          <span
                            className="w-3 h-3 rounded-full shrink-0"
                            style={{ backgroundColor: pmColor }}
                          />
                          <span className="text-sm font-semibold">{pm.pmName}</span>
                          <Badge variant="outline" className="ml-auto text-[10px]">
                            {pm.totalJobs} jobs
                          </Badge>
                        </div>

                        {/* Clusters under this PM */}
                        <div className="ml-4 space-y-1">
                          {pm.clusters.map((cluster, ci) => {
                            const isClusterSelected = selectedClusterId === cluster.clusterId;
                            return (
                              <div
                                key={cluster.clusterId}
                                className={`rounded px-2 py-1.5 cursor-pointer transition-colors ${
                                  isClusterSelected
                                    ? 'ring-1 ring-primary/40 bg-primary/5'
                                    : 'hover:bg-muted/50'
                                }`}
                                onClick={() => {
                                  setSelectedClusterId(isClusterSelected ? null : cluster.clusterId);
                                  setSelectedPlanPM(pm.pmId);
                                }}
                              >
                                <div className="flex items-center gap-1.5">
                                  <span
                                    className="w-2.5 h-2.5 rounded-sm shrink-0"
                                    style={{ backgroundColor: cluster.color }}
                                  />
                                  <span className="text-xs font-medium">
                                    Cluster {ci + 1}
                                  </span>
                                  <Badge
                                    variant="secondary"
                                    className="text-[9px] h-4 px-1"
                                  >
                                    {cluster.clusterInfo.tier}
                                  </Badge>
                                  <span className="text-[10px] text-muted-foreground ml-auto">
                                    {cluster.jobs.length} jobs · {cluster.maxMiles.toFixed(1)}mi
                                  </span>
                                </div>
                                {/* Job names under cluster — clicking selects the cluster, not the individual job */}
                                <div className="ml-4 mt-1 space-y-0.5">
                                  {cluster.jobs.map((j) => (
                                    <div
                                      key={j.job_id}
                                      className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
                                    >
                                      <Badge variant="outline" className="text-[8px] h-3.5 px-1 font-mono tabular-nums">
                                        {j.score.toFixed(0)}
                                      </Badge>
                                      <span className="truncate">{j.customer_name}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}

                          {/* Standalone jobs */}
                          {pm.standaloneJobs.length > 0 && (
                            <div
                              className={`rounded px-2 py-1.5 cursor-pointer transition-colors ${
                                selectedClusterId === `standalone_${pm.pmId}`
                                  ? 'ring-1 ring-amber-400/40 bg-amber-50'
                                  : 'hover:bg-muted/50'
                              }`}
                              onClick={() => {
                                const key = `standalone_${pm.pmId}`;
                                setSelectedClusterId(selectedClusterId === key ? null : key);
                                setSelectedPlanPM(pm.pmId);
                              }}
                            >
                              <div className="flex items-center gap-1.5">
                                <span className="w-2.5 h-2.5 rounded-sm shrink-0 bg-amber-400" />
                                <span className="text-xs font-medium text-amber-700">Standalone</span>
                                <span className="text-[10px] text-muted-foreground ml-auto">
                                  {pm.standaloneJobs.length} jobs
                                </span>
                              </div>
                              <div className="ml-4 mt-1 space-y-0.5">
                                {pm.standaloneJobs.map((j) => (
                                  <div
                                    key={j.job_id}
                                    className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
                                  >
                                    <Badge variant="outline" className="text-[8px] h-3.5 px-1 font-mono tabular-nums">
                                      {j.score.toFixed(0)}
                                    </Badge>
                                    <span className="truncate">{j.customer_name}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {/* Unassigned */}
                  {latestScoringResult?.unassigned_jobs && latestScoringResult.unassigned_jobs.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 px-2 py-1.5">
                        <span className="w-3 h-3 rounded-full shrink-0 bg-gray-300" />
                        <span className="text-sm font-semibold text-muted-foreground">Unassigned</span>
                        <Badge variant="outline" className="ml-auto text-[10px]">
                          {latestScoringResult.unassigned_jobs.length} jobs
                        </Badge>
                      </div>
                      <div className="ml-8 space-y-0.5">
                        {latestScoringResult.unassigned_jobs.map((j) => (
                          <div key={j.job_id} className="text-[10px] text-muted-foreground truncate">
                            {j.customer_name}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
          </div>
        )}

        {/* Job list — status and pm modes */}
        {mapMode !== 'plan' && (
          <>
            <Separator className="shrink-0" />
            <ScrollArea className="flex-1 min-h-0">
              <div className="space-y-2 p-3">
                <p className="text-xs font-semibold text-muted-foreground">
                  {jobs.length} jobs on map
                  {selectedPMFilter !== null && (
                    <span className="text-blue-600 ml-1">
                      (filtered by {pms?.find((p) => p.id === selectedPMFilter)?.name})
                    </span>
                  )}
                </p>
                {jobs.map((job) => (
                  <div
                    key={job.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedJob(job)}
                  >
                    <JobCard job={job} compact />
                  </div>
                ))}
              </div>
            </ScrollArea>
          </>
        )}
      </div>

      {/* Map — full-width on mobile (hidden when list selected), flex on desktop */}
      <div className={`${mobileView === 'map' ? 'flex' : 'hidden'} md:flex flex-1 relative min-h-[300px]`}>
        {GOOGLE_MAPS_API_KEY ? (
          <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
            <Map
              defaultCenter={center}
              defaultZoom={10}
              mapId="roofing-scheduler-map"
              className="w-full h-full"
            >
              {jobs.map((job) => {
                const isDimmed = highlightedJobIds !== null && !highlightedJobIds.has(job.id);
                return (
                  <AdvancedMarker
                    key={job.id}
                    position={{ lat: job.latitude!, lng: job.longitude! }}
                    onClick={() => setSelectedJob(job)}
                  >
                    <MarkerPin
                      color={getMarkerColor(job, mapMode, pmIndex, scoringPMMap, clusterColorMap, jobClusterMap)}
                      label={job.must_build ? '!' : job.score > 0 ? String(Math.round(job.score)) : '•'}
                      dimmed={isDimmed}
                    />
                  </AdvancedMarker>
                );
              })}

              {selectedJob && selectedJob.latitude && selectedJob.longitude && (
                <InfoWindow
                  position={{ lat: selectedJob.latitude, lng: selectedJob.longitude }}
                  onCloseClick={() => setSelectedJob(null)}
                >
                  <div className="max-w-xs">
                    <JobCard job={selectedJob} />
                  </div>
                </InfoWindow>
              )}
            </Map>
          </APIProvider>
        ) : (
          <div className="flex items-center justify-center h-full bg-muted">
            <Card className="max-w-md">
              <CardContent className="p-6 text-center">
                <MapPin className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
                <p className="text-sm text-muted-foreground">
                  Set <code className="bg-muted-foreground/10 px-1 rounded">VITE_GOOGLE_MAPS_API_KEY</code>{' '}
                  in your <code>.env</code> file to enable the map view.
                </p>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
