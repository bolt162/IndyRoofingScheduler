import { useMemo, useState, useCallback } from 'react';
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
  useMap,
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Layers, Users, MapPin } from 'lucide-react';
import type { Job, JobBucket } from '@/types';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '';

// PM color palette
const PM_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
];

function getMarkerColor(job: Job, mapMode: 'cluster' | 'pm', pmIndex: globalThis.Map<number, number>) {
  if (job.must_build) return '#DC2626'; // red
  if (job.standalone_rule) return '#F59E0B'; // amber

  if (mapMode === 'pm' && job.assigned_pm_id) {
    const idx = pmIndex.get(job.assigned_pm_id) ?? 0;
    return PM_COLORS[idx % PM_COLORS.length];
  }

  switch (job.bucket) {
    case 'scheduled': return '#22C55E'; // green
    case 'to_schedule': return '#3B82F6'; // blue
    case 'primary_complete': return '#A855F7'; // purple
    default: return '#6B7280'; // gray
  }
}

function MarkerPin({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex flex-col items-center">
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

export function MapPage() {
  const { mapMode, setMapMode } = useUIStore();
  const [bucketFilter, setBucketFilter] = useState<JobBucket | 'all'>('all');
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);

  const { data: allJobs } = useJobs();
  const { data: pms } = usePMs();

  // Build PM index for color assignment
  const pmIndex = useMemo(() => {
    const m = new globalThis.Map<number, number>();
    pms?.forEach((pm, i) => m.set(pm.id, i));
    return m;
  }, [pms]);

  // Filter jobs with lat/lng
  const jobs = useMemo(() => {
    let result = allJobs?.filter((j) => j.latitude && j.longitude) ?? [];
    if (bucketFilter !== 'all') {
      result = result.filter((j) => j.bucket === bucketFilter);
    }
    return result;
  }, [allJobs, bucketFilter]);

  // Center on Indianapolis by default
  const center = useMemo(() => {
    if (jobs.length === 0) return { lat: 39.7684, lng: -86.1581 };
    const lat = jobs.reduce((s, j) => s + (j.latitude ?? 0), 0) / jobs.length;
    const lng = jobs.reduce((s, j) => s + (j.longitude ?? 0), 0) / jobs.length;
    return { lat, lng };
  }, [jobs]);

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-80 border-r flex flex-col">
        <div className="p-4 space-y-3">
          <h2 className="text-lg font-semibold">Map View</h2>

          {/* Controls */}
          <div className="flex gap-2">
            <Button
              variant={mapMode === 'cluster' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMapMode('cluster')}
            >
              <Layers className="h-3.5 w-3.5 mr-1" />
              Clusters
            </Button>
            <Button
              variant={mapMode === 'pm' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMapMode('pm')}
            >
              <Users className="h-3.5 w-3.5 mr-1" />
              PM Colors
            </Button>
          </div>

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
        </div>

        <Separator />

        {/* PM Legend */}
        {mapMode === 'pm' && pms && (
          <div className="p-4">
            <p className="text-xs font-semibold text-muted-foreground mb-2">PM Legend</p>
            <div className="space-y-1">
              {pms.filter((p) => p.is_active).map((pm, i) => (
                <div key={pm.id} className="flex items-center gap-2 text-xs">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: PM_COLORS[i % PM_COLORS.length] }}
                  />
                  {pm.name}
                </div>
              ))}
            </div>
          </div>
        )}

        <Separator />

        {/* Job list in sidebar */}
        <ScrollArea className="flex-1 p-3">
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground">
              {jobs.length} jobs on map
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
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        {GOOGLE_MAPS_API_KEY ? (
          <APIProvider apiKey={GOOGLE_MAPS_API_KEY}>
            <Map
              defaultCenter={center}
              defaultZoom={10}
              mapId="roofing-scheduler-map"
              className="w-full h-full"
            >
              {jobs.map((job) => (
                <AdvancedMarker
                  key={job.id}
                  position={{ lat: job.latitude!, lng: job.longitude! }}
                  onClick={() => setSelectedJob(job)}
                >
                  <MarkerPin
                    color={getMarkerColor(job, mapMode, pmIndex)}
                    label={job.must_build ? '!' : job.score > 0 ? String(Math.round(job.score)) : '•'}
                  />
                </AdvancedMarker>
              ))}

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
