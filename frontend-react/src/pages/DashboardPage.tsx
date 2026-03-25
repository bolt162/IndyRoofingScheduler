import { useState } from 'react';
import {
  RefreshCw, Brain, Zap, ClipboardList,
  Package, CheckCircle2, Clock, Eye, Truck,
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
import { useJobs, useBucketCounts } from '@/api/jobs';
import { useRunScoring, useScanNotes } from '@/api/scoring';
import { useCheckAllWeather } from '@/api/weather';
import { useUIStore } from '@/stores/ui-store';
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
  const { activeBucket, setActiveBucket } = useUIStore();
  const { data: counts, isLoading: countsLoading } = useBucketCounts();
  const { data: jobs, isLoading: jobsLoading } = useJobs(
    activeBucket === 'all' ? undefined : activeBucket
  );

  const runScoring = useRunScoring();
  const scanNotes = useScanNotes();
  const checkWeather = useCheckAllWeather();

  const [scoringResult, setScoringResult] = useState<string | null>(null);

  const mustBuildJobs = jobs?.filter((j) => j.must_build) ?? [];

  const handleRunScoring = async () => {
    try {
      const result = await runScoring.mutateAsync({});
      setScoringResult(result.ai_explanation);
      toast.success(`Scored ${result.recommendations.length} jobs`);
    } catch {
      toast.error('Scoring failed');
    }
  };

  const handleScanNotes = async () => {
    try {
      const result = await scanNotes.mutateAsync();
      toast.success(`Scanned ${result.scanned ?? 0} jobs`);
    } catch {
      toast.error('Note scanning failed');
    }
  };

  const handleCheckWeather = async () => {
    try {
      await checkWeather.mutateAsync();
      toast.success('Weather check complete');
    } catch {
      toast.error('Weather check failed');
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Job scheduling overview and AI tools
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleScanNotes}
            disabled={scanNotes.isPending}
          >
            <Brain className="h-4 w-4 mr-1.5" />
            {scanNotes.isPending ? 'Scanning...' : 'Scan Notes (AI)'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheckWeather}
            disabled={checkWeather.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-1.5 ${checkWeather.isPending ? 'animate-spin' : ''}`} />
            Check Weather
          </Button>
          <Button
            size="sm"
            onClick={handleRunScoring}
            disabled={runScoring.isPending}
          >
            <Zap className="h-4 w-4 mr-1.5" />
            {runScoring.isPending ? 'Scoring...' : 'Run Scoring'}
          </Button>
        </div>
      </div>

      {/* Bucket summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {bucketCards.map(({ key, label, icon: Icon, color }) => (
          <Card
            key={key}
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setActiveBucket(key)}
          >
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <Icon className={`h-5 w-5 ${color}`} />
                <span className="text-2xl font-bold tabular-nums">
                  {countsLoading ? '—' : (counts?.[key] ?? 0)}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">{label}</p>
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
              {scoringResult}
            </pre>
          </CardContent>
        </Card>
      )}

      <Separator />

      {/* Job Queue with bucket tabs */}
      <div>
        <Tabs
          value={activeBucket}
          onValueChange={(v) => setActiveBucket(v as JobBucket | 'all')}
        >
          <TabsList className="mb-3">
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
        </Tabs>

        {jobsLoading ? (
          <div className="text-sm text-muted-foreground py-8 text-center">Loading jobs...</div>
        ) : (
          <JobList jobs={jobs ?? []} />
        )}
      </div>
    </div>
  );
}
