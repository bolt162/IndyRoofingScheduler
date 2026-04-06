import { useState } from 'react';
import { toast } from 'sonner';
import {
  Users, Truck, Sliders, Ruler, Cloud, Brain, Calendar, Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useSettings, useUpdateSetting, usePMs, useAddPM, useCrews, useAddCrew, useResetDB } from '@/api/settings';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';

export function SettingsPage() {
  const { data: settings } = useSettings();
  const updateSetting = useUpdateSetting();
  const { data: pms } = usePMs();
  const addPM = useAddPM();
  const { data: crews } = useCrews();
  const addCrew = useAddCrew();
  const resetDB = useResetDB();
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  // New PM form
  const [newPMName, setNewPMName] = useState('');
  const [newPMBaseline, setNewPMBaseline] = useState(3);
  const [newPMMax, setNewPMMax] = useState(5);

  // New crew form
  const [newCrewName, setNewCrewName] = useState('');
  const [newCrewSpecialties, setNewCrewSpecialties] = useState('');

  const handleUpdateSetting = async (key: string, value: string) => {
    try {
      await updateSetting.mutateAsync({ key, value });
      toast.success(`Updated ${key}`);
    } catch {
      toast.error(`Failed to update ${key}`);
    }
  };

  const handleAddPM = async () => {
    if (!newPMName) return;
    try {
      await addPM.mutateAsync({ name: newPMName, baseline: newPMBaseline, maxCap: newPMMax });
      setNewPMName('');
      toast.success('PM added');
    } catch {
      toast.error('Failed to add PM');
    }
  };

  const handleAddCrew = async () => {
    if (!newCrewName) return;
    try {
      const specialties = newCrewSpecialties ? newCrewSpecialties.split(',').map((s) => s.trim()) : [];
      await addCrew.mutateAsync({ name: newCrewName, specialties });
      setNewCrewName('');
      setNewCrewSpecialties('');
      toast.success('Crew added');
    } catch {
      toast.error('Failed to add crew');
    }
  };

  const getSetting = (key: string) => settings?.[key]?.value ?? '';

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Configure scheduling rules, teams, and thresholds</p>
      </div>

      <Tabs defaultValue="pms">
        <TabsList className="grid grid-cols-4 lg:grid-cols-7 w-full">
          <TabsTrigger value="pms"><Users className="h-3.5 w-3.5 mr-1" />PMs</TabsTrigger>
          <TabsTrigger value="crews"><Truck className="h-3.5 w-3.5 mr-1" />Crews</TabsTrigger>
          <TabsTrigger value="scoring"><Sliders className="h-3.5 w-3.5 mr-1" />Scoring</TabsTrigger>
          <TabsTrigger value="distance"><Ruler className="h-3.5 w-3.5 mr-1" />Distance</TabsTrigger>
          <TabsTrigger value="weather"><Cloud className="h-3.5 w-3.5 mr-1" />Weather</TabsTrigger>
          <TabsTrigger value="ai"><Brain className="h-3.5 w-3.5 mr-1" />AI Rules</TabsTrigger>
          <TabsTrigger value="system"><Calendar className="h-3.5 w-3.5 mr-1" />System</TabsTrigger>
        </TabsList>

        {/* PMs Tab */}
        <TabsContent value="pms">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">PM Roster</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Existing PMs */}
              <div className="space-y-2">
                {pms?.map((pm) => (
                  <div key={pm.id} className="flex items-center gap-4 p-3 bg-muted rounded-md">
                    <span className="font-medium text-sm flex-1">{pm.name}</span>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>Baseline: {pm.baseline_capacity}</span>
                      <span>Max: {pm.max_capacity}</span>
                    </div>
                    <Badge variant={pm.is_active ? 'default' : 'secondary'}>
                      {pm.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                ))}
              </div>

              <Separator />

              {/* Add PM form */}
              <div className="space-y-3">
                <p className="text-sm font-medium">Add New PM</p>
                <div className="grid grid-cols-4 gap-3">
                  <div className="col-span-2">
                    <Label>Name</Label>
                    <Input
                      value={newPMName}
                      onChange={(e) => setNewPMName(e.target.value)}
                      placeholder="PM Name"
                    />
                  </div>
                  <div>
                    <Label>Baseline</Label>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      value={newPMBaseline}
                      onChange={(e) => setNewPMBaseline(parseInt(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label>Max</Label>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      value={newPMMax}
                      onChange={(e) => setNewPMMax(parseInt(e.target.value))}
                    />
                  </div>
                </div>
                <Button size="sm" onClick={handleAddPM} disabled={!newPMName || addPM.isPending}>
                  Add PM
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Crews Tab */}
        <TabsContent value="crews">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Crew Roster</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {crews?.map((crew) => (
                <div key={crew.id} className="flex items-center gap-4 p-3 bg-muted rounded-md">
                  <span className="font-medium text-sm flex-1">{crew.name}</span>
                  <div className="flex gap-1">
                    {crew.specialties?.map((s) => (
                      <Badge key={s} variant="outline" className="text-[10px]">{s}</Badge>
                    ))}
                  </div>
                  <Badge variant={crew.is_active ? 'default' : 'secondary'}>
                    {crew.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              ))}

              <Separator />

              <div className="space-y-3">
                <p className="text-sm font-medium">Add New Crew</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Name</Label>
                    <Input
                      value={newCrewName}
                      onChange={(e) => setNewCrewName(e.target.value)}
                      placeholder="Crew Name"
                    />
                  </div>
                  <div>
                    <Label>Specialties (comma-separated)</Label>
                    <Input
                      value={newCrewSpecialties}
                      onChange={(e) => setNewCrewSpecialties(e.target.value)}
                      placeholder="roofing, siding, gutters"
                    />
                  </div>
                </div>
                <Button size="sm" onClick={handleAddCrew} disabled={!newCrewName || addCrew.isPending}>
                  Add Crew
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Scoring Weights Tab */}
        <TabsContent value="scoring">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Scoring Weights</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {[
                { key: 'weight_days_in_queue', label: 'Days in Queue' },
                { key: 'weight_payment_type', label: 'Payment Type' },
                { key: 'weight_trade_complexity', label: 'Trade Type' },
                { key: 'weight_proximity', label: 'Proximity Cluster' },
                { key: 'weight_material_weather', label: 'Material-Weather' },
                { key: 'weight_must_build', label: 'Must Build' },
                { key: 'weight_rescheduled', label: 'Rescheduled Bump' },
                { key: 'weight_permit_confirmed', label: 'Permit Confirmed' },
                { key: 'weight_duration_confirmed', label: 'Duration Confirmed' },
              ].map(({ key, label }) => {
                const val = parseInt(getSetting(key)) || 10;
                return (
                  <div key={key} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm">{label}</Label>
                      <span className="text-sm font-mono tabular-nums">{val}</span>
                    </div>
                    <Slider
                      value={[val]}
                      min={0}
                      max={50}
                      step={1}
                      onValueCommitted={(val: number | readonly number[]) => {
                        const v = Array.isArray(val) ? val[0] : val;
                        handleUpdateSetting(key, String(v));
                      }}
                    />
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Distance Tab */}
        <TabsContent value="distance">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Distance Tier Rules</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                { key: 'cluster_tier_1_miles', label: 'Tier 1 — Tight Cluster (miles)', desc: 'Max 5 jobs/PM' },
                { key: 'cluster_tier_2_miles', label: 'Tier 2 — Close Cluster (miles)', desc: 'Max 4 jobs/PM' },
                { key: 'cluster_tier_3_miles', label: 'Tier 3 — Standard (miles)', desc: 'Max 3 jobs/PM' },
                { key: 'cluster_tier_4_miles', label: 'Tier 4 — Extended (miles)', desc: 'Max 1-2 jobs/PM' },
                { key: 'cluster_tier_5_miles', label: 'Tier 5 — Standalone (miles)', desc: 'Standalone rule applies' },
              ].map(({ key, label, desc }) => (
                <div key={key} className="grid grid-cols-3 gap-4 items-center">
                  <div>
                    <Label className="text-sm">{label}</Label>
                    <p className="text-xs text-muted-foreground">{desc}</p>
                  </div>
                  <Input
                    type="number"
                    className="col-span-1"
                    defaultValue={getSetting(key)}
                    onBlur={(e) => handleUpdateSetting(key, e.target.value)}
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Weather Thresholds Tab */}
        <TabsContent value="weather">
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Material Weather Thresholds</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {[
                  { key: 'asphalt', label: 'Asphalt Shingles' },
                  { key: 'polymer', label: 'Polymer Modified' },
                  { key: 'tpo', label: 'TPO / EPDM' },
                  { key: 'coating', label: 'Coatings' },
                  { key: 'wood_shake', label: 'Wood Shake' },
                  { key: 'slate', label: 'Slate' },
                  { key: 'metal', label: 'Metal' },
                  { key: 'siding', label: 'Siding' },
                ].map(({ key, label }) => (
                  <div key={key} className="space-y-2 p-3 bg-muted rounded-md">
                    <p className="text-sm font-medium">{label}</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div>
                        <Label className="text-xs">Min Temp (°F)</Label>
                        <Input
                          type="number"
                          defaultValue={getSetting(`weather_${key}_min_temp`)}
                          onBlur={(e) => handleUpdateSetting(`weather_${key}_min_temp`, e.target.value)}
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Max Wind (mph)</Label>
                        <Input
                          type="number"
                          defaultValue={getSetting(`weather_${key}_max_wind`)}
                          onBlur={(e) => handleUpdateSetting(`weather_${key}_max_wind`, e.target.value)}
                        />
                      </div>
                      {(key === 'tpo' || key === 'coating') && (
                        <div>
                          <Label className="text-xs">Rain Window (hrs)</Label>
                          <Input
                            type="number"
                            defaultValue={getSetting(`weather_${key}_rain_window_hrs`)}
                            onBlur={(e) => handleUpdateSetting(`weather_${key}_rain_window_hrs`, e.target.value)}
                          />
                        </div>
                      )}
                      {key === 'coating' && (
                        <div>
                          <Label className="text-xs">Max Humidity (%)</Label>
                          <Input
                            type="number"
                            defaultValue={getSetting('weather_coating_max_humidity')}
                            onBlur={(e) => handleUpdateSetting('weather_coating_max_humidity', e.target.value)}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Automated Weather Checks</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs">Morning Check Time (24hr)</Label>
                    <Input
                      defaultValue={getSetting('weather_morning_check_time')}
                      onBlur={(e) => handleUpdateSetting('weather_morning_check_time', e.target.value)}
                      placeholder="06:00"
                    />
                    <p className="text-[10px] text-muted-foreground mt-1">Checks all scheduled jobs for today + tomorrow</p>
                  </div>
                  <div>
                    <Label className="text-xs">Night-Before Check Time (24hr)</Label>
                    <Input
                      defaultValue={getSetting('bamwx_check_time')}
                      onBlur={(e) => handleUpdateSetting('bamwx_check_time', e.target.value)}
                      placeholder="20:00"
                    />
                    <p className="text-[10px] text-muted-foreground mt-1">Final authority check on tomorrow's builds (uses Clarity Wx)</p>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">5am spot check runs automatically every day on today's builds.</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* AI Rules Tab */}
        <TabsContent value="ai">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI Scoring Rules</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Write plain English rules that the AI scoring engine will follow when ranking jobs.
              </p>
              <Textarea
                className="min-h-[300px] font-mono text-sm"
                defaultValue={getSetting('ai_custom_rules')}
                onBlur={(e) => handleUpdateSetting('ai_custom_rules', e.target.value)}
                placeholder="Example: Always prioritize insurance jobs that have been in queue for more than 30 days. If two jobs are in the same cluster, prefer the one with a confirmed permit."
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* System Tab */}
        <TabsContent value="system">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">System Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label>PM Baseline Capacity</Label>
                  <Input
                    type="number"
                    defaultValue={getSetting('pm_baseline_capacity')}
                    onBlur={(e) => handleUpdateSetting('pm_baseline_capacity', e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>PM Max Capacity</Label>
                  <Input
                    type="number"
                    defaultValue={getSetting('pm_max_capacity')}
                    onBlur={(e) => handleUpdateSetting('pm_max_capacity', e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Secondary Trade Yellow Threshold (days)</Label>
                  <Input
                    type="number"
                    defaultValue={getSetting('secondary_yellow_days')}
                    onBlur={(e) => handleUpdateSetting('secondary_yellow_days', e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Secondary Trade Red Threshold (days)</Label>
                  <Input
                    type="number"
                    defaultValue={getSetting('secondary_red_days')}
                    onBlur={(e) => handleUpdateSetting('secondary_red_days', e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Sit Time Average (days)</Label>
                  <Input
                    type="number"
                    defaultValue={getSetting('sit_time_average')}
                    onBlur={(e) => handleUpdateSetting('sit_time_average', e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>BamWx Check Time (24hr)</Label>
                  <Input
                    defaultValue={getSetting('bamwx_check_time')}
                    onBlur={(e) => handleUpdateSetting('bamwx_check_time', e.target.value)}
                    placeholder="20:00"
                  />
                </div>
                <div className="space-y-2">
                  <Label>JN Sync Interval (minutes)</Label>
                  <Input
                    type="number"
                    min={1}
                    defaultValue={getSetting('jn_sync_interval_minutes')}
                    onBlur={(e) => handleUpdateSetting('jn_sync_interval_minutes', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    How often to auto-sync jobs from JobNimbus. Takes effect on next cycle.
                  </p>
                </div>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Blocked Weeks</Label>
                <p className="text-xs text-muted-foreground">
                  Current blocked weeks: {getSetting('blocked_weeks') || 'None'}
                </p>
                <Input
                  placeholder="Add date (YYYY-MM-DD)"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const input = e.currentTarget;
                      const current = getSetting('blocked_weeks');
                      const updated = current ? `${current},${input.value}` : input.value;
                      handleUpdateSetting('blocked_weeks', updated);
                      input.value = '';
                    }
                  }}
                />
              </div>

              <Separator />

              {/* Reset Database */}
              <div className="space-y-2">
                <Label className="text-destructive">Danger Zone</Label>
                <p className="text-xs text-muted-foreground">
                  Reset the entire database. This will delete all jobs, PMs, crews, notes, and plans. Settings will be re-seeded to defaults.
                </p>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setResetConfirmOpen(true)}
                >
                  Reset Database
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Reset DB Confirmation Dialog */}
      <Dialog open={resetConfirmOpen} onOpenChange={setResetConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-destructive">Reset Database</DialogTitle>
            <DialogDescription>
              This will permanently delete ALL data: jobs, PMs, crews, notes, schedule plans, and scoring results. Settings will be reset to defaults. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setResetConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={resetDB.isPending}
              onClick={async () => {
                try {
                  await resetDB.mutateAsync();
                  toast.success('Database reset successfully');
                  setResetConfirmOpen(false);
                } catch {
                  toast.error('Failed to reset database');
                }
              }}
            >
              {resetDB.isPending ? 'Resetting...' : 'Yes, Reset Everything'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
