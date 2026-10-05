import { useState } from 'react';
import { Lock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useMe } from '@/api/auth';
import { useActivity, type ActivityRow } from '@/api/activity';

const KIND_LABEL: Record<string, string> = {
  user: 'Someone did', job: 'Automatic', email: 'Email', note: 'JobNimbus note', error: 'Error', api: 'Outside call',
};
const KIND_STYLE: Record<string, string> = {
  user: 'bg-blue-100 text-blue-900', job: 'bg-slate-100 text-slate-800', email: 'bg-green-100 text-green-900',
  note: 'bg-purple-100 text-purple-900', error: 'bg-red-100 text-red-900', api: 'bg-slate-100 text-slate-800',
};

function when(iso: string) {
  return new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit',
  });
}

function duration(ms: number | null) {
  if (ms === null) return '';
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function ActivityPage() {
  const { data: me, isLoading: meLoading } = useMe();
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const allowed = Boolean(me?.owner_or_admin);
  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useActivity(allowed ? { kind, status, q } : { kind: '__none__' });

  if (meLoading) return <div className="p-6 text-sm">Loading...</div>;
  if (!allowed) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
        <Lock className="h-4 w-4" /> The activity log is only available to the owner and admins.
      </div>
    );
  }

  const rows: ActivityRow[] = data?.pages.flatMap((p) => p.rows) ?? [];

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">Activity Log <Lock className="h-4 w-4 text-muted-foreground" /></h1>
        <p className="text-sm text-muted-foreground">
          Everything the scheduler does: changes people make, automatic runs and the outside calls they made,
          emails, notes written to JobNimbus, and errors. Visible only to the owner and admins. Kept 90 days.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Type" className="rounded-md border bg-background px-3 py-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All types</option>
          {Object.entries(KIND_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select aria-label="Result" className="rounded-md border bg-background px-3 py-2 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any result</option>
          <option value="ok">OK</option>
          <option value="error">Errors only</option>
          <option value="skipped">Skipped</option>
        </select>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQ(search.trim()); }}>
          <Input aria-label="Search" className="w-64" placeholder="Search (customer, person, action)" value={search} onChange={(e) => setSearch(e.target.value)} />
          <Button type="submit" variant="outline" size="sm">Search</Button>
        </form>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[150px]">When</TableHead>
                <TableHead className="w-[130px]">Type</TableHead>
                <TableHead>What</TableHead>
                <TableHead>Details</TableHead>
                <TableHead>Who</TableHead>
                <TableHead className="text-right">Took</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <TableRow><TableCell colSpan={6}>Loading...</TableCell></TableRow>}
              {isError && <TableRow><TableCell colSpan={6} className="text-red-700">Couldn't load the activity log.</TableCell></TableRow>}
              {!isLoading && rows.length === 0 && <TableRow><TableCell colSpan={6}>Nothing logged yet for these filters.</TableCell></TableRow>}
              {rows.map((r) => (
                <TableRow key={r.id} className={r.status === 'error' ? 'bg-red-50/60' : ''}>
                  <TableCell className="whitespace-nowrap text-xs tabular-nums">{when(r.at)}</TableCell>
                  <TableCell>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${KIND_STYLE[r.kind] ?? ''}`}>{KIND_LABEL[r.kind] ?? r.kind}</span>
                    {r.status !== 'ok' && <Badge variant="outline" className="ml-1">{r.status}</Badge>}
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.action}
                    {r.job_id && <span className="ml-1 text-xs text-muted-foreground">(job {r.job_id})</span>}
                  </TableCell>
                  <TableCell className="max-w-[420px] break-words text-xs text-muted-foreground">{r.detail}</TableCell>
                  <TableCell className="text-xs">{r.actor ?? (r.kind === 'job' ? 'system' : '')}</TableCell>
                  <TableCell className="whitespace-nowrap text-right text-xs tabular-nums">{duration(r.duration_ms)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {hasNextPage && (
        <Button variant="outline" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? 'Loading...' : 'Load older'}
        </Button>
      )}
    </div>
  );
}
