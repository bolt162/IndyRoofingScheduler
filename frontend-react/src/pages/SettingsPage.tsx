import { useState } from 'react';
import { toast } from 'sonner';
import {
  Users, Truck, Sliders, Ruler, Cloud, Brain, Calendar, Clock, Pencil, Trash2, Pause, Play, ArrowUp, ArrowDown, Trophy, Medal, Award,
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
import { useSettings, useUpdateSetting, usePMs, useAddPM, useUpdatePM, useDeletePM, useCrews, useAddCrew, useUpdateCrew, useDeleteCrew, useResetDB } from '@/api/settings';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';

export function SettingsPage() {
  const { data: settings } = useSettings();
  const updateSetting = useUpdateSetting();
  const { data: pms } = usePMs();
  const addPM = useAddPM();
  const updatePM = useUpdatePM();
  const deletePM = useDeletePM();
  const { data: crews } = useCrews();
  const addCrew = useAddCrew();
  const updateCrew = useUpdateCrew();
  const deleteCrew = useDeleteCrew();
  const resetDB = useResetDB();
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  // Crew edit state
  const [editingCrewId, setEditingCrewId] = useState<number | null>(null);
  const [editCrewName, setEditCrewName] = useState('');
  const [editCrewSpecialties, setEditCrewSpecialties] = useState('');
  const [editCrewRank, setEditCrewRank] = useState('');
  const [editCrewNotes, setEditCrewNotes] = useState('');

  // New crew — rank/notes extras
  const [newCrewRank, setNewCrewRank] = useState<number>(0);
  const [newCrewNotes, setNewCrewNotes] = useState('');

  // PM edit state
  const [editingPMId, setEditingPMId] = useState<number | null>(null);
  const [editPMName, setEditPMName] = useState('');
  const [editPMBaseline, setEditPMBaseline] = useState(3);
  const [editPMMax, setEditPMMax] = useState(5);

  // New PM form
  const [newPMName, setNewPMName] = useState('');
  const [newPMBaseline, setNewPMBaseline] = useState(3);
  const [newPMMax, setNewPMMax] = useState(5);

  // New crew form
  const [newCrewName, setNewCrewName] = useState('');
  const [newCrewSpecialties, setNewCrewSpecialties] = useState('');

  // AI Rules draft state — save/cancel pattern (doesn't auto-save on blur)
  const savedAIRules = settings?.['ai_custom_rules']?.value ?? '';
  const [aiRulesDraft, setAIRulesDraft] = useState(savedAIRules);
  const [aiRulesInitialized, setAIRulesInitialized] = useState(false);

  // Initialize draft from settings once loaded
  if (!aiRulesInitialized && settings) {
    setAIRulesDraft(savedAIRules);
    setAIRulesInitialized(true);
  }

  const aiRulesDirty = aiRulesDraft !== savedAIRules;

  const handleSaveAIRules = async () => {
    try {
      await updateSetting.mutateAsync({ key: 'ai_custom_rules', value: aiRulesDraft });
      toast.success('AI rules saved');
    } catch {
      toast.error('Failed to save AI rules');
    }
  };

  const handleCancelAIRules = () => {
    setAIRulesDraft(savedAIRules);
  };

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
      const specialties = newCrewSpecialties ? newCrewSpecialties.split(',').map((s) => s.trim()).filter(Boolean) : [];
      // Auto-assign rank if not specified: next rank after highest existing rank < 999
      const rank = newCrewRank > 0 ? newCrewRank : (Math.max(
        0,
        ...(crews ?? []).filter(c => c.rank < 999).map(c => c.rank)
      ) + 1);
      await addCrew.mutateAsync({
        name: newCrewName,
        specialties,
        rank,
        notes: newCrewNotes || null,
      });
      setNewCrewName('');
      setNewCrewSpecialties('');
      setNewCrewRank(0);
      setNewCrewNotes('');
      toast.success('Crew added');
    } catch {
      toast.error('Failed to add crew');
    }
  };

  const getSetting = (key: string) => settings?.[key]?.value ?? '';

  // Swap rank with neighbor in the sorted crew list. direction: 'up' or 'down'.
  const swapCrewRank = (crewId: number, direction: 'up' | 'down') => {
    if (!crews) return;
    const sorted = [...crews].sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
    const idx = sorted.findIndex(c => c.id === crewId);
    if (idx === -1) return;
    const neighborIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (neighborIdx < 0 || neighborIdx >= sorted.length) return;
    const me = sorted[idx];
    const neighbor = sorted[neighborIdx];
    // Swap their ranks. If either is 999 (unranked), give them real ranks.
    const myNewRank = neighbor.rank < 999 ? neighbor.rank : neighborIdx + 1;
    const neighborNewRank = me.rank < 999 ? me.rank : idx + 1;
    updateCrew.mutate({ id: me.id, update: { rank: myNewRank } });
    updateCrew.mutate({ id: neighbor.id, update: { rank: neighborNewRank } });
  };

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-xs md:text-sm text-muted-foreground">Configure scheduling rules, teams, and thresholds</p>
      </div>

      <Tabs defaultValue="pms">
        <div className="overflow-x-auto -mx-1 px-1">
          <TabsList className="inline-flex w-max lg:grid lg:grid-cols-7 lg:w-full">
          <TabsTrigger value="pms"><Users className="h-3.5 w-3.5 mr-1" />PMs</TabsTrigger>
          <TabsTrigger value="crews"><Truck className="h-3.5 w-3.5 mr-1" />Crews</TabsTrigger>
          <TabsTrigger value="scoring"><Sliders className="h-3.5 w-3.5 mr-1" />Scoring</TabsTrigger>
          <TabsTrigger value="distance"><Ruler className="h-3.5 w-3.5 mr-1" />Distance</TabsTrigger>
          <TabsTrigger value="weather"><Cloud className="h-3.5 w-3.5 mr-1" />Weather</TabsTrigger>
          <TabsTrigger value="ai"><Brain className="h-3.5 w-3.5 mr-1" />AI Rules</TabsTrigger>
          <TabsTrigger value="system"><Calendar className="h-3.5 w-3.5 mr-1" />System</TabsTrigger>
          </TabsList>
        </div>

        {/* PMs Tab */}
        <TabsContent value="pms">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">PM Roster</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Existing PMs */}
              <div className="space-y-2">
                {pms?.length === 0 && (
                  <p className="text-sm text-muted-foreground">No PMs added yet.</p>
                )}
                {pms?.map((pm) => (
                  <div key={pm.id} className="p-3 bg-muted rounded-md space-y-2">
                    {editingPMId === pm.id ? (
                      /* Edit mode */
                      <div className="space-y-2">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div className="col-span-2">
                            <Label className="text-xs">Name</Label>
                            <Input
                              value={editPMName}
                              onChange={(e) => setEditPMName(e.target.value)}
                            />
                          </div>
                          <div>
                            <Label className="text-xs">Baseline</Label>
                            <Input
                              type="number"
                              min={1}
                              max={10}
                              value={editPMBaseline}
                              onChange={(e) => setEditPMBaseline(parseInt(e.target.value) || 0)}
                            />
                          </div>
                          <div>
                            <Label className="text-xs">Max</Label>
                            <Input
                              type="number"
                              min={1}
                              max={10}
                              value={editPMMax}
                              onChange={(e) => setEditPMMax(parseInt(e.target.value) || 0)}
                            />
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            className="h-7 text-xs"
                            disabled={updatePM.isPending || !editPMName}
                            onClick={() => {
                              updatePM.mutate({
                                id: pm.id,
                                update: {
                                  name: editPMName,
                                  baseline_capacity: editPMBaseline,
                                  max_capacity: editPMMax,
                                },
                              }, {
                                onSuccess: () => {
                                  toast.success(`Updated ${editPMName}`);
                                  setEditingPMId(null);
                                },
                                onError: () => toast.error('Failed to update PM'),
                              });
                            }}
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs"
                            onClick={() => setEditingPMId(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      /* Display mode */
                      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm">{pm.name}</span>
                            <Badge variant={pm.is_active ? 'default' : 'secondary'} className="text-[10px]">
                              {pm.is_active ? 'Active' : 'Inactive — On leave'}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground">
                            <span>Baseline: <strong className="text-foreground">{pm.baseline_capacity}</strong> jobs/day</span>
                            <span>Max: <strong className="text-foreground">{pm.max_capacity}</strong> jobs/day</span>
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 md:shrink-0">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => {
                              updatePM.mutate({
                                id: pm.id,
                                update: { is_active: !pm.is_active },
                              }, {
                                onSuccess: () => toast.success(pm.is_active ? `${pm.name} deactivated` : `${pm.name} activated`),
                              });
                            }}
                          >
                            {pm.is_active ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                            {pm.is_active ? 'Deactivate' : 'Activate'}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => {
                              setEditingPMId(pm.id);
                              setEditPMName(pm.name);
                              setEditPMBaseline(pm.baseline_capacity);
                              setEditPMMax(pm.max_capacity);
                            }}
                          >
                            <Pencil className="h-3 w-3" />
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1 text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            onClick={() => {
                              if (confirm(`Delete PM "${pm.name}"? This cannot be undone.\n\nNote: Deletion is blocked if any jobs are still assigned to this PM. Use Deactivate instead for temporary leave.`)) {
                                deletePM.mutate(pm.id, {
                                  onSuccess: () => toast.success(`${pm.name} deleted`),
                                  onError: (err: any) => toast.error(
                                    err?.response?.data?.detail || 'Failed to delete PM'
                                  ),
                                });
                              }
                            }}
                          >
                            <Trash2 className="h-3 w-3" />
                            Delete
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <Separator />

              {/* Add PM form */}
              <div className="space-y-3">
                <p className="text-sm font-medium">Add New PM</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
              <CardTitle className="text-base">Crew Roster (ranked best first)</CardTitle>
              <p className="text-xs text-muted-foreground">
                Rank crews from best to worst. Top-ranked crews are auto-assigned to the most complex jobs ("Michael Jordan first").
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {crews?.length === 0 && (
                <p className="text-sm text-muted-foreground">No crews added yet.</p>
              )}
              {crews?.map((crew, idx) => {
                const sortedCrews = [...(crews ?? [])].sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
                const sortedIdx = sortedCrews.findIndex(c => c.id === crew.id);
                const isFirst = sortedIdx === 0;
                const isLast = sortedIdx === sortedCrews.length - 1;
                const rankIcon = crew.rank === 1 ? <Trophy className="h-4 w-4 text-yellow-500" />
                  : crew.rank === 2 ? <Medal className="h-4 w-4 text-gray-400" />
                  : crew.rank === 3 ? <Award className="h-4 w-4 text-amber-700" />
                  : null;
                return (
                <div key={crew.id} className="p-3 bg-muted rounded-md space-y-2">
                  {editingCrewId === crew.id ? (
                    /* Edit mode */
                    <div className="space-y-2">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="md:col-span-2">
                          <Label className="text-xs">Name</Label>
                          <Input
                            value={editCrewName}
                            onChange={(e) => setEditCrewName(e.target.value)}
                          />
                        </div>
                        <div>
                          <Label className="text-xs">Rank (1 = best)</Label>
                          <Input
                            type="number"
                            min={1}
                            value={editCrewRank}
                            onChange={(e) => setEditCrewRank(e.target.value)}
                          />
                          {editCrewRank === '' && (
                            <p className="text-[10px] text-red-600 mt-0.5">Rank can't be empty</p>
                          )}
                        </div>
                      </div>
                      <div>
                        <Label className="text-xs">Specialties (comma-separated)</Label>
                        <Input
                          value={editCrewSpecialties}
                          onChange={(e) => setEditCrewSpecialties(e.target.value)}
                          placeholder="roofing, slate, tpo"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Notes (strengths, warranties, history)</Label>
                        <Textarea
                          value={editCrewNotes}
                          onChange={(e) => setEditCrewNotes(e.target.value)}
                          placeholder="e.g., handles complex roofs, few warranties, steep pitch expert"
                          className="min-h-[60px]"
                        />
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          className="h-7 text-xs"
                          disabled={updateCrew.isPending || !editCrewName || editCrewRank === ''}
                          onClick={() => {
                            const parsedRank = parseInt(editCrewRank) || 999;
                            updateCrew.mutate({
                              id: crew.id,
                              update: {
                                name: editCrewName,
                                specialties: editCrewSpecialties
                                  ? editCrewSpecialties.split(',').map(s => s.trim()).filter(Boolean)
                                  : [],
                                rank: parsedRank,
                                notes: editCrewNotes || null,
                              },
                            }, {
                              onSuccess: () => {
                                toast.success(`Updated ${editCrewName}`);
                                setEditingCrewId(null);
                              },
                              onError: () => toast.error('Failed to update crew'),
                            });
                          }}
                        >
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          onClick={() => setEditingCrewId(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    /* Display mode */
                    <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          {rankIcon}
                          <Badge
                            variant="outline"
                            className={
                              crew.rank === 1 ? 'text-[10px] bg-yellow-50 text-yellow-800 border-yellow-400 font-bold'
                              : crew.rank < 999 ? 'text-[10px] bg-blue-50 text-blue-700 border-blue-300'
                              : 'text-[10px] text-muted-foreground'
                            }
                          >
                            {crew.rank < 999 ? `Rank #${crew.rank}` : 'Unranked'}
                          </Badge>
                          <span className="font-medium text-sm">{crew.name}</span>
                          <Badge variant={crew.is_active ? 'default' : 'secondary'} className="text-[10px]">
                            {crew.is_active ? 'Active' : 'Inactive — On leave'}
                          </Badge>
                        </div>
                        {crew.specialties && crew.specialties.length > 0 ? (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {crew.specialties.map((s) => (
                              <Badge key={s} variant="outline" className="text-[10px] bg-blue-50 text-blue-700">
                                {s}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[10px] text-muted-foreground mt-1">No specialties assigned</p>
                        )}
                        {crew.notes && (
                          <p className="text-[11px] text-muted-foreground italic mt-1.5 whitespace-pre-wrap">
                            {crew.notes}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-row md:flex-col md:items-end gap-1.5 md:shrink-0 flex-wrap">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 w-6 p-0"
                            title="Move up (promote rank)"
                            disabled={isFirst || updateCrew.isPending}
                            onClick={() => swapCrewRank(crew.id, 'up')}
                          >
                            <ArrowUp className="h-3 w-3" />
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 w-6 p-0"
                            title="Move down (demote rank)"
                            disabled={isLast || updateCrew.isPending}
                            onClick={() => swapCrewRank(crew.id, 'down')}
                          >
                            <ArrowDown className="h-3 w-3" />
                          </Button>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => {
                              updateCrew.mutate({
                                id: crew.id,
                                update: { is_active: !crew.is_active },
                              }, {
                                onSuccess: () => toast.success(crew.is_active ? `${crew.name} deactivated` : `${crew.name} activated`),
                              });
                            }}
                          >
                            {crew.is_active ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                            {crew.is_active ? 'Deactivate' : 'Activate'}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => {
                              setEditingCrewId(crew.id);
                              setEditCrewName(crew.name);
                              setEditCrewSpecialties(crew.specialties?.join(', ') || '');
                              setEditCrewRank(String(crew.rank));
                              setEditCrewNotes(crew.notes || '');
                            }}
                          >
                            <Pencil className="h-3 w-3" />
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1 text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            onClick={() => {
                              if (confirm(`Delete crew "${crew.name}"?`)) {
                                deleteCrew.mutate(crew.id);
                              }
                            }}
                          >
                            <Trash2 className="h-3 w-3" />
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                );
              })}

              <Separator />

              <div className="space-y-3">
                <p className="text-sm font-medium">Add New Crew</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="md:col-span-2">
                    <Label>Name</Label>
                    <Input
                      value={newCrewName}
                      onChange={(e) => setNewCrewName(e.target.value)}
                      placeholder="Crew Name (e.g., Louise)"
                    />
                  </div>
                  <div>
                    <Label>Rank (optional)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={newCrewRank || ''}
                      onChange={(e) => setNewCrewRank(parseInt(e.target.value) || 0)}
                      placeholder="Auto"
                    />
                  </div>
                </div>
                <div>
                  <Label>Specialties (comma-separated)</Label>
                  <Input
                    value={newCrewSpecialties}
                    onChange={(e) => setNewCrewSpecialties(e.target.value)}
                    placeholder="roofing, slate, tpo"
                  />
                </div>
                <div>
                  <Label>Notes (optional — strengths, history, warranties)</Label>
                  <Textarea
                    value={newCrewNotes}
                    onChange={(e) => setNewCrewNotes(e.target.value)}
                    placeholder="e.g., handles complex roofs, few warranties, steep pitch expert"
                    className="min-h-[60px]"
                  />
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
                <div key={key} className="grid grid-cols-1 md:grid-cols-3 gap-2 md:gap-4 md:items-center">
                  <div className="md:col-span-2">
                    <Label className="text-sm">{label}</Label>
                    <p className="text-xs text-muted-foreground">{desc}</p>
                  </div>
                  <Input
                    type="number"
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
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              <CardTitle className="text-base flex items-center justify-between">
                <span>AI Scoring Rules</span>
                {aiRulesDirty && (
                  <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-300">
                    Unsaved changes
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Write plain English rules that the AI scoring engine will follow when ranking jobs. Click Save to apply.
              </p>
              <Textarea
                className="min-h-[300px] font-mono text-sm"
                value={aiRulesDraft}
                onChange={(e) => setAIRulesDraft(e.target.value)}
                placeholder="Example: Always prioritize insurance jobs that have been in queue for more than 30 days. If two jobs are in the same cluster, prefer the one with a confirmed permit."
              />
              <div className="flex items-center justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCancelAIRules}
                  disabled={!aiRulesDirty || updateSetting.isPending}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveAIRules}
                  disabled={!aiRulesDirty || updateSetting.isPending}
                >
                  {updateSetting.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
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
