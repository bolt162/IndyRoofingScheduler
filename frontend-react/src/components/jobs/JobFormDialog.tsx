import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { MATERIAL_LABELS } from '@/types';
import type { Job, MaterialType, TradeType } from '@/types';

const TRADE_OPTIONS: { value: TradeType; label: string }[] = [
  { value: 'roofing', label: 'Roofing' },
  { value: 'siding', label: 'Siding' },
  { value: 'gutters', label: 'Gutters' },
  { value: 'windows', label: 'Windows' },
  { value: 'paint', label: 'Paint' },
  { value: 'interior', label: 'Interior' },
  { value: 'other', label: 'Other' },
];

const MATERIAL_OPTIONS = Object.entries(MATERIAL_LABELS).map(([value, label]) => ({
  value: value as MaterialType,
  label,
}));

interface JobFormData {
  customer_name: string;
  address: string;
  job_type: string;
  payment_type: string;
  primary_trade: string;
  secondary_trades: string[];
  material_type: string;
  square_footage: string; // Keep as string for input, convert on submit
  sales_rep: string;
  duration_days: string;
  notes: string;
}

interface JobFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: 'create' | 'edit';
  job?: Job | null; // Pre-fill for edit mode
  onSubmit: (data: Record<string, any>) => void;
  isPending?: boolean;
}

function jobToFormData(job: Job): JobFormData {
  return {
    customer_name: job.customer_name || '',
    address: job.address || '',
    job_type: job.job_type || 'retail',
    payment_type: job.payment_type || 'cash',
    primary_trade: job.primary_trade || 'roofing',
    secondary_trades: job.secondary_trades || [],
    material_type: job.material_type || 'asphalt',
    square_footage: job.square_footage ? String(job.square_footage) : '',
    sales_rep: job.sales_rep || '',
    duration_days: String(job.duration_days || 1),
    notes: job.jn_notes_raw || '',
  };
}

const DEFAULT_FORM: JobFormData = {
  customer_name: '',
  address: '',
  job_type: 'retail',
  payment_type: 'cash',
  primary_trade: 'roofing',
  secondary_trades: [],
  material_type: 'asphalt',
  square_footage: '',
  sales_rep: '',
  duration_days: '1',
  notes: '',
};

export function JobFormDialog({ open, onOpenChange, mode, job, onSubmit, isPending }: JobFormDialogProps) {
  const [form, setForm] = useState<JobFormData>(DEFAULT_FORM);

  useEffect(() => {
    if (open) {
      if (mode === 'edit' && job) {
        setForm(jobToFormData(job));
      } else {
        setForm(DEFAULT_FORM);
      }
    }
  }, [open, mode, job]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (mode === 'create') {
      onSubmit({
        customer_name: form.customer_name,
        address: form.address,
        job_type: form.job_type,
        payment_type: form.payment_type,
        primary_trade: form.primary_trade,
        secondary_trades: form.secondary_trades,
        material_type: form.material_type,
        square_footage: form.square_footage ? parseFloat(form.square_footage) : null,
        sales_rep: form.sales_rep || null,
        duration_days: parseInt(form.duration_days) || 1,
        notes: form.notes || null,
      });
    } else {
      // Edit mode: only send changed fields
      const original = job ? jobToFormData(job) : DEFAULT_FORM;
      const changes: Record<string, any> = {};

      if (form.customer_name !== original.customer_name) changes.customer_name = form.customer_name;
      if (form.address !== original.address) changes.address = form.address;
      if (form.job_type !== original.job_type) changes.job_type = form.job_type;
      if (form.payment_type !== original.payment_type) changes.payment_type = form.payment_type;
      if (form.primary_trade !== original.primary_trade) changes.primary_trade = form.primary_trade;
      if (JSON.stringify(form.secondary_trades) !== JSON.stringify(original.secondary_trades)) {
        changes.secondary_trades = form.secondary_trades;
      }
      if (form.material_type !== original.material_type) changes.material_type = form.material_type;
      if (form.square_footage !== original.square_footage) {
        changes.square_footage = form.square_footage ? parseFloat(form.square_footage) : null;
      }
      if (form.sales_rep !== original.sales_rep) changes.sales_rep = form.sales_rep || null;
      if (form.duration_days !== original.duration_days) {
        changes.duration_days = parseInt(form.duration_days) || 1;
      }
      if (form.notes !== original.notes) changes.notes = form.notes || null;

      if (Object.keys(changes).length > 0) {
        onSubmit(changes);
      } else {
        onOpenChange(false);
      }
    }
  };

  const toggleSecondaryTrade = (trade: string) => {
    setForm(prev => ({
      ...prev,
      secondary_trades: prev.secondary_trades.includes(trade)
        ? prev.secondary_trades.filter(t => t !== trade)
        : [...prev.secondary_trades, trade],
    }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? 'Create New Job' : 'Edit Job'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Customer Name */}
          <div className="space-y-1.5">
            <Label htmlFor="customer_name">Customer Name *</Label>
            <Input
              id="customer_name"
              value={form.customer_name}
              onChange={e => setForm(f => ({ ...f, customer_name: e.target.value }))}
              required
              placeholder="John Smith"
            />
          </div>

          {/* Address */}
          <div className="space-y-1.5">
            <Label htmlFor="address">Address *</Label>
            <Input
              id="address"
              value={form.address}
              onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
              required
              placeholder="123 Main St, Indianapolis, IN 46201"
            />
          </div>

          {/* Job Type + Payment Type — side by side */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Job Type</Label>
              <Select value={form.job_type} onValueChange={v => setForm(f => ({ ...f, job_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="retail">Retail</SelectItem>
                  <SelectItem value="insurance">Insurance</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Payment Type *</Label>
              <Select value={form.payment_type} onValueChange={v => setForm(f => ({ ...f, payment_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Cash</SelectItem>
                  <SelectItem value="finance">Finance</SelectItem>
                  <SelectItem value="insurance">Insurance</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Primary Trade */}
          <div className="space-y-1.5">
            <Label>Primary Trade *</Label>
            <Select value={form.primary_trade} onValueChange={v => setForm(f => ({ ...f, primary_trade: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {TRADE_OPTIONS.map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Secondary Trades — checkboxes */}
          <div className="space-y-1.5">
            <Label>Secondary Trades</Label>
            <div className="flex flex-wrap gap-3">
              {TRADE_OPTIONS
                .filter(t => t.value !== form.primary_trade)
                .map(t => (
                  <label key={t.value} className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <Checkbox
                      checked={form.secondary_trades.includes(t.value)}
                      onCheckedChange={() => toggleSecondaryTrade(t.value)}
                    />
                    {t.label}
                  </label>
                ))}
            </div>
          </div>

          {/* Material Type + Square Footage — side by side */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Material Type *</Label>
              <Select value={form.material_type} onValueChange={v => setForm(f => ({ ...f, material_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {MATERIAL_OPTIONS.map(m => (
                    <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Square Footage</Label>
              <Input
                type="number"
                value={form.square_footage}
                onChange={e => setForm(f => ({ ...f, square_footage: e.target.value }))}
                placeholder="e.g. 2500"
                min={0}
              />
            </div>
          </div>

          {/* Sales Rep + Duration — side by side */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Sales Rep</Label>
              <Input
                value={form.sales_rep}
                onChange={e => setForm(f => ({ ...f, sales_rep: e.target.value }))}
                placeholder="Rep name"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Duration (days)</Label>
              <Input
                type="number"
                value={form.duration_days}
                onChange={e => setForm(f => ({ ...f, duration_days: e.target.value }))}
                min={1}
                max={14}
              />
            </div>
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Job description, scope details, special instructions..."
              rows={3}
            />
          </div>

          {/* Submit */}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? (mode === 'create' ? 'Creating...' : 'Saving...') : (mode === 'create' ? 'Create Job' : 'Save Changes')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
