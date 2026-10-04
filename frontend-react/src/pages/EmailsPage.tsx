import { useState } from 'react';
import { toast } from 'sonner';
import { CloudRain, Eye, Pause, Play, Mail, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  useEmailPreview, useEmailStatus, useJobEmail, usePauseJob, useProducts, useReviewProduct,
  useSaveTeamMember, useSendPreviewNow, useTeam, useWeatherToggle,
  type PreviewRow, type TeamMember,
} from '@/api/emails';

const MODE_STYLE: Record<string, string> = {
  off: 'bg-muted text-muted-foreground',
  test: 'bg-amber-100 text-amber-900',
  live: 'bg-green-100 text-green-900',
};
const MODE_TEXT: Record<string, string> = {
  off: 'Off: nothing sends',
  test: 'Test: every email goes to Aaron only',
  live: 'Live: sending to customers',
};

function fmtDate(iso: string) {
  return new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

export function EmailsPage() {
  const { data: status } = useEmailStatus();
  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Customer Emails</h1>
        {status && (
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${MODE_STYLE[status.mode]}`}>
            {MODE_TEXT[status.mode]}
          </span>
        )}
      </div>
      <Tabs defaultValue="thursday">
        <TabsList>
          <TabsTrigger value="thursday">This Thursday</TabsTrigger>
          <TabsTrigger value="team">Team</TabsTrigger>
          <TabsTrigger value="products">Products</TabsTrigger>
          <TabsTrigger value="log">Send log</TabsTrigger>
        </TabsList>
        <TabsContent value="thursday"><ThursdayTab /></TabsContent>
        <TabsContent value="team"><TeamTab /></TabsContent>
        <TabsContent value="products"><ProductsTab /></TabsContent>
        <TabsContent value="log"><LogTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function ThursdayTab() {
  const { data: status } = useEmailStatus();
  const { data: preview, isLoading, isError, refetch } = useEmailPreview();
  const weather = useWeatherToggle();
  const pause = usePauseJob();
  const sendNow = useSendPreviewNow();
  const [viewJob, setViewJob] = useState<number | null>(null);

  const weatherOn = Boolean(status?.weather_slowdown_date);
  const toggleWeather = (on: boolean) =>
    weather.mutate(on, {
      onSuccess: () => toast.success(on ? 'Weather slowdown email is on for this Thursday' : 'Weather slowdown email is off'),
    });
  const togglePause = (row: PreviewRow) => {
    const paused = row.reason.startsWith('suppressed');
    pause.mutate({ jobId: row.job_id, pause: !paused }, {
      onSuccess: () => toast.success(paused ? `${row.customer} will get emails again` : `${row.customer} is paused`),
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Next send</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{preview ? preview.sending : '...'} emails</div>
            <div className="text-xs text-muted-foreground">{status ? fmtDate(status.next_thursday) : ''}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-sm font-medium"><CloudRain className="h-4 w-4" /> Weather slowdown</CardTitle></CardHeader>
          <CardContent className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Replaces this Thursday's weekly email with the weather update. Switches itself off after.
            </span>
            <Switch checked={weatherOn} onCheckedChange={toggleWeather} disabled={weather.isPending} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Preview email</CardTitle></CardHeader>
          <CardContent className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">Goes out Wednesdays at 2pm to Aaron, Greg, Luke, and each rep.</span>
            <Button size="sm" variant="outline" disabled={sendNow.isPending}
              onClick={() => sendNow.mutate(undefined, {
                onSuccess: () => toast.success('Preview sent'),
                onError: () => toast.error('Only admins can send the preview by hand'),
              })}>
              <Send className="mr-1 h-4 w-4" /> Send now
            </Button>
          </CardContent>
        </Card>
      </div>

      {preview && preview.fix.length > 0 && (
        <Card className="border-amber-300">
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Please fix in JobNimbus</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            {preview.fix.map((r) => <div key={r.job_id}>{r.customer}: {r.reason}</div>)}
          </CardContent>
        </Card>
      )}

      {preview && preview.long_wait.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Waiting 10+ weeks</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            {preview.long_wait.map((r) => (
              <div key={r.customer}>{r.customer}: {r.weeks} weeks ({r.rep || 'no rep'})</div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead>Trade</TableHead>
                <TableHead>Rep</TableHead>
                <TableHead>Email they'll get</TableHead>
                <TableHead>Why</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={6}>Looking up every queued customer in JobNimbus. This can take up to a minute...</TableCell></TableRow>
              )}
              {isError && (
                <TableRow><TableCell colSpan={6} className="text-red-700">
                  Couldn't build the preview. <Button size="sm" variant="outline" onClick={() => refetch()}>Try again</Button>
                </TableCell></TableRow>
              )}
              {preview && preview.rows.length === 0 && (
                <TableRow><TableCell colSpan={6}>No customers in the build queue yet. The JobNimbus sync runs every 15 minutes.</TableCell></TableRow>
              )}
              {preview?.rows.map((r) => {
                const paused = r.reason.startsWith('suppressed');
                return (
                  <TableRow key={r.job_id} className={r.template ? '' : 'text-muted-foreground'}>
                    <TableCell className="font-medium">{r.customer}</TableCell>
                    <TableCell>{r.trade.replace('_', ' ')}</TableCell>
                    <TableCell>{r.rep}</TableCell>
                    <TableCell>{r.template ? <Badge variant="secondary">{r.label}</Badge> : 'Nothing'}</TableCell>
                    <TableCell className="text-xs">
                      {r.reason}
                      {r.notes.length > 0 && <div className="text-amber-700">{r.notes.join('; ')}</div>}
                    </TableCell>
                    <TableCell className="space-x-1 text-right">
                      {r.template && (
                        <Button size="sm" variant="ghost" title="View email" aria-label="View email" onClick={() => setViewJob(r.job_id)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => togglePause(r)}
                        title={paused ? 'Resume emails' : 'Pause emails'} aria-label={paused ? 'Resume emails' : 'Pause emails'}>
                        {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <EmailDialog jobId={viewJob} onClose={() => setViewJob(null)} />
    </div>
  );
}

function EmailDialog({ jobId, onClose }: { jobId: number | null; onClose: () => void }) {
  const { data, isLoading } = useJobEmail(jobId);
  return (
    <Dialog open={jobId !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><Mail className="h-4 w-4" />{data?.subject ?? 'Email'}</DialogTitle></DialogHeader>
        {isLoading && <div className="text-sm">Loading...</div>}
        {data?.html && <iframe title="email" className="h-[60vh] w-full rounded border bg-white" srcDoc={data.html} sandbox="" />}
        {data && !data.html && <div className="text-sm text-muted-foreground">{data.reason}</div>}
      </DialogContent>
    </Dialog>
  );
}

const ROLE_LABEL: Record<string, string> = { rep: 'Sales rep', pm: 'Project manager', ops: 'Operations', owner: 'Owner' };

function TeamTab() {
  const { data: team } = useTeam();
  const save = useSaveTeamMember();
  const [editing, setEditing] = useState<Partial<TeamMember> | null>(null);

  const submit = () => {
    if (!editing?.jn_name || !editing.display_name) return toast.error('Name is required');
    save.mutate({ role: 'rep', is_active: true, ...editing }, {
      onSuccess: () => { toast.success('Saved'); setEditing(null); },
      onError: () => toast.error('Could not save'),
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">
          Only active people are ever named in customer emails. Customers of anyone else get the office number.
        </CardTitle>
        <Button size="sm" onClick={() => setEditing({ role: 'rep', is_active: true })}>Add person</Button>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name customers see</TableHead>
              <TableHead>Name in JobNimbus</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Active</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {team?.map((m) => (
              <TableRow key={m.id} className={m.is_active ? '' : 'text-muted-foreground'}>
                <TableCell className="font-medium">{m.display_name}</TableCell>
                <TableCell>{m.jn_name}</TableCell>
                <TableCell>{ROLE_LABEL[m.role] ?? m.role}</TableCell>
                <TableCell>{m.phone ?? ''}</TableCell>
                <TableCell className="text-xs">{m.email ?? ''}</TableCell>
                <TableCell>{m.is_active ? 'Yes' : 'No'}</TableCell>
                <TableCell><Button size="sm" variant="ghost" onClick={() => setEditing(m)}>Edit</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing?.id ? 'Edit person' : 'Add person'}</DialogTitle></DialogHeader>
          {editing && (
            <div className="space-y-3">
              <Input placeholder="Name customers see (e.g. Jimmy Clinger)" value={editing.display_name ?? ''}
                onChange={(e) => setEditing({ ...editing, display_name: e.target.value })} />
              <Input placeholder="Name exactly as JobNimbus shows it" value={editing.jn_name ?? ''}
                onChange={(e) => setEditing({ ...editing, jn_name: e.target.value })} />
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={editing.role ?? 'rep'}
                onChange={(e) => setEditing({ ...editing, role: e.target.value as TeamMember['role'] })}>
                {Object.entries(ROLE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <Input placeholder="Phone" value={editing.phone ?? ''} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} />
              <Input placeholder="Email" value={editing.email ?? ''} onChange={(e) => setEditing({ ...editing, email: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={editing.is_active ?? true} onCheckedChange={(v) => setEditing({ ...editing, is_active: v })} />
                Active (turn off when someone leaves)
              </label>
              <Button className="w-full" onClick={submit} disabled={save.isPending}>Save</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

const CLASS_LABEL = (c: number | null) => (c === 4 ? 'Class 4' : c === 3 ? 'Class 3' : 'No rating');
const COMP_LABEL: Record<string, string> = { oxidized: 'Oxidized asphalt', polymer_modified: 'Polymer modified' };

function ProductsTab() {
  const { data: products } = useProducts();
  const review = useReviewProduct();
  const act = (id: number, approve: boolean) =>
    review.mutate({ id, approve }, { onSuccess: () => toast.success(approve ? 'Approved' : 'Rejected') });

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Shingles we didn't already know. Thorough research is approved automatically; the rest waits here.
          Until approved, customers get the insurance tip without an impact rating.
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>Finding</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Sources</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {products?.length === 0 && <TableRow><TableCell colSpan={5}>No new products yet.</TableCell></TableRow>}
            {products?.map((p) => {
              const sources: { url: string }[] = p.sources ? JSON.parse(p.sources) : [];
              return (
                <TableRow key={p.id}>
                  <TableCell>
                    <div className="font-medium">{p.display_name ?? p.raw_text}</div>
                    <div className="text-xs text-muted-foreground">{p.summary}</div>
                  </TableCell>
                  <TableCell>{CLASS_LABEL(p.impact_class)}, {COMP_LABEL[p.composition ?? ''] ?? 'composition unknown'}</TableCell>
                  <TableCell><Badge variant="secondary">{p.status.replace('_', ' ')}</Badge></TableCell>
                  <TableCell className="max-w-[220px] text-xs">
                    {sources.map((s) => <div key={s.url} className="truncate"><a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.url}</a></div>)}
                  </TableCell>
                  <TableCell className="space-x-1 whitespace-nowrap text-right">
                    {p.status !== 'approved' && <Button size="sm" onClick={() => act(p.id, true)}>Approve</Button>}
                    {p.status !== 'rejected' && <Button size="sm" variant="outline" onClick={() => act(p.id, false)}>Reject</Button>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function LogTab() {
  const { data: status } = useEmailStatus();
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>To</TableHead>
              <TableHead>Mode</TableHead>
              <TableHead>Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {status?.recent.length === 0 && <TableRow><TableCell colSpan={5}>Nothing sent yet.</TableCell></TableRow>}
            {status?.recent.map((l, i) => (
              <TableRow key={i}>
                <TableCell className="whitespace-nowrap text-xs">{fmtDate(l.at)}</TableCell>
                <TableCell className="text-xs">{l.subject}</TableCell>
                <TableCell className="text-xs">{l.recipient}</TableCell>
                <TableCell>{l.mode}</TableCell>
                <TableCell>
                  <Badge variant={l.result === 'sent' ? 'secondary' : 'outline'}>{l.result}</Badge>
                  {l.detail && <div className="text-xs text-muted-foreground">{l.detail}</div>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
