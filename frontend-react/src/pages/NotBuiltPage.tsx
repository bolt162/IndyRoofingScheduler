import { useState } from 'react';
import { toast } from 'sonner';
import {
  AlertTriangle, XCircle, RotateCcw, Layers,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { JobCard } from '@/components/jobs/JobCard';
import { useJobs, useMarkNotBuilt, useUpdateJob } from '@/api/jobs';
import { NOT_BUILT_REASONS } from '@/types';
import type { Job } from '@/types';

export function NotBuiltPage() {
  const { data: allJobs } = useJobs();
  const markNotBuilt = useMarkNotBuilt();
  const updateJob = useUpdateJob();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [reason, setReason] = useState('');
  const [detail, setDetail] = useState('');

  // Scope change fields
  const [newDuration, setNewDuration] = useState(2);
  const [retainCrew, setRetainCrew] = useState(true);

  const scheduledJobs = allJobs?.filter((j) => j.bucket === 'scheduled') ?? [];
  const multiDayJobs = allJobs?.filter((j) => j.is_multi_day && j.bucket === 'scheduled') ?? [];
  const recentlyNotBuilt = allJobs?.filter(
    (j) => j.bucket === 'to_schedule' && j.rescheduled_count > 0
  )?.sort((a, b) => b.rescheduled_count - a.rescheduled_count) ?? [];

  const isScope = reason === 'Scope Change';

  const openDialog = (job: Job) => {
    setSelectedJob(job);
    setReason('');
    setDetail('');
    setNewDuration(2);
    setRetainCrew(true);
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    if (!selectedJob || !reason) return;

    try {
      if (isScope) {
        // Scope change: update to multi-day, then mark not built
        await updateJob.mutateAsync({
          id: selectedJob.id,
          update: {
            duration_days: newDuration,
            duration_confirmed: true,
          },
        });
      }

      await markNotBuilt.mutateAsync({
        id: selectedJob.id,
        request: {
          reason,
          detail: isScope
            ? `Scope change to ${newDuration}-day build. ${retainCrew ? 'Retain same crew.' : 'Crew reassignment needed.'} ${detail}`
            : detail || undefined,
        },
      });

      toast.success(`${selectedJob.customer_name} marked as Not Built`);
      setDialogOpen(false);
    } catch {
      toast.error('Failed to mark job as Not Built');
    }
  };

  return (
    <div className="flex flex-col gap-4 md:gap-6 p-3 md:p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Not Built Workflow</h1>
        <p className="text-sm text-muted-foreground">
          Manage scheduled jobs that cannot be built, scope changes, and multi-day tracking
        </p>
      </div>

      {/* Scheduled Jobs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <XCircle className="h-4 w-4" />
            Scheduled Jobs ({scheduledJobs.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {scheduledJobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No scheduled jobs</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {scheduledJobs.map((job) => (
                <div key={job.id} className="flex flex-col gap-1.5">
                  <JobCard job={job} compact />
                  <Button
                    variant="destructive"
                    size="sm"
                    className="w-full h-7 text-xs"
                    onClick={() => openDialog(job)}
                  >
                    Mark Not Built
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Multi-Day In Progress */}
      {multiDayJobs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Multi-Day Jobs In Progress ({multiDayJobs.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {multiDayJobs.map((job) => (
                <div key={job.id}>
                  <JobCard job={job} compact />
                  <div className="mt-1 px-1">
                    <Badge variant="outline" className="text-xs">
                      Day {job.multi_day_current} of {job.duration_days}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recently Not Built */}
      {recentlyNotBuilt.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <RotateCcw className="h-4 w-4" />
              Recently Not Built ({recentlyNotBuilt.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {recentlyNotBuilt.map((job) => (
                <div key={job.id}>
                  <JobCard job={job} compact />
                  {job.rescheduled_count >= 2 && (
                    <div className="flex items-center gap-1 mt-1 px-1">
                      <AlertTriangle className="h-3 w-3 text-amber-500" />
                      <span className="text-[10px] text-amber-600">
                        Rescheduled {job.rescheduled_count}× — customer communication recommended
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Not Built Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mark Not Built — {selectedJob?.customer_name}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Reason</Label>
              <Select value={reason} onValueChange={(v) => setReason(v ?? '')}>
                <SelectTrigger>
                  <SelectValue placeholder="Select reason..." />
                </SelectTrigger>
                <SelectContent>
                  {NOT_BUILT_REASONS.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {isScope && (
              <>
                <Separator />
                <div className="space-y-3 bg-muted p-3 rounded-md">
                  <p className="text-sm font-medium">Scope Change → Multi-Day</p>
                  <div className="space-y-2">
                    <Label>New Duration (days)</Label>
                    <Input
                      type="number"
                      min={2}
                      value={newDuration}
                      onChange={(e) => setNewDuration(parseInt(e.target.value) || 2)}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="retain-crew"
                      checked={retainCrew}
                      onCheckedChange={(v) => setRetainCrew(v === true)}
                    />
                    <Label htmlFor="retain-crew" className="text-sm">
                      Retain same crew for Day 2+
                    </Label>
                  </div>
                </div>
              </>
            )}

            <div className="space-y-2">
              <Label>Additional Detail</Label>
              <Textarea
                placeholder="Optional detail..."
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleSubmit}
              disabled={!reason || markNotBuilt.isPending}
            >
              {markNotBuilt.isPending ? 'Processing...' : 'Mark Not Built'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
