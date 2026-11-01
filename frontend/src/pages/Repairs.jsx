import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import api from '../services/api';
import { parseServerDate } from '../utils/dates';

// What staff can tap in "What needs fixing" (more than one can be picked)
const REPAIR_TYPES = [
  'Screen replacement',
  'Battery replacement',
  'Charging port',
  'Back glass / housing',
  'Camera',
  'Speaker / microphone',
  'Buttons',
  'Water damage',
  'Not turning on',
  'Software / reset',
  'Network / signal',
  'Other',
];

const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });

// Every status belongs to a stage; the stage decides the color.
const STAGES = [
  { key: 'line', label: 'In line', statuses: ['Pending'],
    badge: 'bg-amber-100 text-amber-800', bar: 'border-l-amber-400', dot: 'bg-amber-400' },
  { key: 'repairing', label: 'Being repaired', statuses: ['Diagnosis', 'In Progress'],
    badge: 'bg-blue-100 text-blue-800', bar: 'border-l-blue-500', dot: 'bg-blue-500' },
  { key: 'pickup', label: 'Waiting for pickup', statuses: ['Ready for Pickup'],
    badge: 'bg-terrace-100 text-terrace-800', bar: 'border-l-terrace-500', dot: 'bg-terrace-500' },
  { key: 'done', label: 'Picked up', statuses: ['Released', 'Completed'],
    badge: 'bg-stone-200 text-stone-700', bar: 'border-l-stone-500', dot: 'bg-stone-500' },
  { key: 'cancelled', label: 'Cancelled', statuses: ['Cancelled'],
    badge: 'bg-stone-100 text-stone-400', bar: 'border-l-stone-200', dot: 'bg-stone-300' },
];

const stageOf = (status) => STAGES.find((s) => s.statuses.includes(status)) || STAGES[0];

// Friendlier names for the stored status values
const STATUS_LABELS = {
  Pending: 'In line',
  Diagnosis: 'Checking the problem',
  'In Progress': 'Being repaired',
  'Ready for Pickup': 'Waiting for pickup',
  Released: 'Picked up',
  Cancelled: 'Cancelled',
};

// The one-click "next step" for each status
const NEXT_STEP = {
  Pending: { label: 'Start repair', status: 'In Progress' },
  Diagnosis: { label: 'Start repair', status: 'In Progress' },
  'In Progress': { label: 'Mark done', status: 'Ready for Pickup' },
  'Ready for Pickup': { label: 'Picked up', status: 'Released' },
};

const inputClass =
  'w-full px-3 py-2 border border-stone-300 rounded-md text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500';

const jobNumber = (id) => `#${String(id).padStart(4, '0')}`;

function errorMessage(err, fallback) {
  const data = err.response?.data;
  if (data?.detail?.error?.message) return data.detail.error.message;
  if (data?.error?.message) return data.error.message;
  if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg.replace(/^Value error, /, '');
  return fallback;
}

function receivedLabel(value) {
  const date = parseServerDate(value);
  if (Number.isNaN(date.getTime())) return '—';
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return `Today ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
  }
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function RepairStatusBadge({ status }) {
  const stage = stageOf(status);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${stage.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${stage.dot}`} />
      {STATUS_LABELS[status] || status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Customer name field — suggests existing customers while typing; anything
// not picked from the list is saved as a new customer.
// ---------------------------------------------------------------------------
function CustomerNameField({ inputRef, name, customerId, onType, onPick }) {
  const [matches, setMatches] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const term = name.trim();
    if (customerId || term.length < 2) {
      setMatches([]);
      return undefined;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await api.get('/customers', { params: { q: term, limit: 6 } });
        setMatches(res.data);
      } catch {
        setMatches([]);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [name, customerId]);

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={name}
        onChange={(e) => {
          onType(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Name"
        autoComplete="off"
        className={inputClass}
      />
      {open && matches.length > 0 && (
        <div className="absolute z-20 mt-1 w-full rounded-md border border-stone-200 bg-white shadow-lg divide-y divide-stone-100">
          <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-stone-400">Returning customer?</p>
          {matches.map((c) => (
            <button
              key={c.id}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onPick(c);
                setOpen(false);
              }}
              className="w-full text-left px-3 py-2 hover:bg-stone-50"
            >
              <span className="text-sm font-medium text-stone-800">{c.name || 'No name'}</span>
              <span className="ml-2 text-xs text-stone-500">{c.phone_number}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quick add — always on the page; saves with Enter and clears for the next one
// ---------------------------------------------------------------------------
const emptyIntake = {
  name: '',
  phone: '',
  customerId: null,
  device: '',
  repairType: '',
  details: '',
  cost: '',
};

function QuickAddRepair({ deviceSuggestions, onCreated }) {
  const [form, setForm] = useState(emptyIntake);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const [saving, setSaving] = useState(false);
  const nameRef = useRef(null);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSaved('');

    if (!form.name.trim()) return setError("Enter the customer's name.");
    if (!form.device.trim()) return setError('Enter the phone model.');
    if (!form.repairType && !form.details.trim()) return setError('Choose what needs fixing or write the problem in the notes.');
    if (!form.customerId && !form.phone.trim()) return setError("Add the customer's phone number so you can call them when it's ready.");

    const body = {
      device_model: form.device.trim(),
      repair_type: form.repairType || null,
      issue_description: form.details.trim(),
      estimated_cost: parseFloat(form.cost) || 0,
    };
    if (form.customerId) {
      body.customer_id = form.customerId;
    } else {
      const parts = form.name.trim().split(/\s+/).filter(Boolean);
      body.first_name = parts.length > 1 ? parts.slice(0, -1).join(' ') : parts[0] || null;
      body.last_name = parts.length > 1 ? parts[parts.length - 1] : null;
      body.phone_number = form.phone.trim();
    }

    setSaving(true);
    try {
      const res = await api.post('/repairs', body);
      const r = res.data;
      setSaved(`${jobNumber(r.id)} added — ${r.customer_name || 'customer'}, ${r.device_model}`);
      setForm(emptyIntake);
      onCreated();
      nameRef.current?.focus();
    } catch (err) {
      setError(errorMessage(err, 'Could not add the repair. Please try again.'));
    } finally {
      setSaving(false);
    }
  };

  const label = 'block text-xs font-semibold text-stone-600 mb-1';
  const required = <span className="text-brand-600">*</span>;

  return (
    <form onSubmit={submit} className="bg-white rounded-lg border border-stone-200 shadow-sm">
      <div className="px-5 py-3 border-b border-stone-200">
        <h2 className="font-display text-lg font-bold uppercase tracking-wide text-stone-800">New repair</h2>
      </div>

      <div className="p-5 space-y-3">
        {error && (
          <div className="px-3 py-2 bg-brand-50 border border-brand-200 text-brand-800 text-sm rounded-md">{error}</div>
        )}
        {saved && (
          <div className="px-3 py-2 bg-terrace-50 border border-terrace-200 text-terrace-800 text-sm rounded-md">✓ {saved}</div>
        )}

        <label className="block">
          <span className={label}>Customer name {required}</span>
          <CustomerNameField
            inputRef={nameRef}
            name={form.name}
            customerId={form.customerId}
            onType={(name) => setForm((f) => ({ ...f, name, customerId: null }))}
            onPick={(c) => setForm((f) => ({ ...f, name: c.name || '', phone: c.phone_number, customerId: c.id }))}
          />
        </label>
        <label className="block">
          <span className={label}>
            Phone number {form.customerId && <span className="font-normal text-terrace-700">· returning customer</span>}
          </span>
          <input
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value, customerId: null }))}
            placeholder="09xx xxx xxxx"
            inputMode="tel"
            className={inputClass}
          />
        </label>
        <label className="block">
          <span className={label}>Phone model {required}</span>
          <input value={form.device} onChange={set('device')} list="repair-devices"
            placeholder="e.g. Redmi Note 13" autoComplete="off" className={inputClass} />
          <datalist id="repair-devices">
            {deviceSuggestions.map((d) => <option key={d} value={d} />)}
          </datalist>
        </label>
        <label className="block">
          <span className={label}>What needs fixing</span>
          <select value={form.repairType} onChange={set('repairType')}
            className={`${inputClass} ${form.repairType ? '' : 'text-stone-400'}`}>
            <option value="">Choose…</option>
            {REPAIR_TYPES.map((type) => <option key={type} value={type} className="text-stone-800">{type}</option>)}
          </select>
        </label>
        <label className="block">
          <span className={label}>Notes for the technician</span>
          <textarea value={form.details} onChange={set('details')} rows={2}
            placeholder="e.g. cracked at the top corner, passcode 1234"
            className={`${inputClass} resize-none`} />
        </label>
        <label className="block">
          <span className={label}>Est. cost (₱)</span>
          <input type="number" min="0" step="0.01" value={form.cost} onChange={set('cost')}
            placeholder="0" className={inputClass} />
        </label>

        <button
          type="submit"
          disabled={saving}
          className="w-full px-6 py-2.5 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 disabled:bg-brand-300 rounded-md transition-colors"
        >
          {saving ? 'Adding…' : 'Add repair'}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Inline Editable Cost
// ---------------------------------------------------------------------------
function InlineCost({ value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  const handleSave = () => {
    const parsed = parseFloat(draft);
    if (isNaN(parsed) || parsed < 0) {
      setDraft(value);
      setEditing(false);
      return;
    }
    onSave(parsed);
    setEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') {
      setDraft(value);
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <div className="relative inline-flex items-center">
        <span className="absolute left-2 text-stone-500 text-xs">₱</span>
        <input
          type="number"
          step="0.01"
          min="0"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={handleSave}
          onKeyDown={handleKeyDown}
          autoFocus
          className="w-24 pl-5 pr-2 py-1 text-xs border border-brand-400 rounded-md focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className="text-sm text-stone-700 hover:text-brand-600 hover:underline cursor-pointer text-left tabular-nums"
      title="Click to edit"
    >
      {peso.format(Number(value))}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Paid / Unpaid — click to switch
// ---------------------------------------------------------------------------
function PaidToggle({ paid, onChange }) {
  return (
    <button
      onClick={() => onChange(!paid)}
      title={paid ? 'Paid — click to mark as unpaid' : 'Not paid yet — click to mark as paid'}
      className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wide whitespace-nowrap border transition-colors ${
        paid
          ? 'bg-terrace-600 text-white border-terrace-600 hover:bg-terrace-700'
          : 'bg-white text-brand-700 border-brand-300 hover:bg-brand-50'
      }`}
    >
      {paid ? '✓ Paid' : 'Unpaid'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Status: one-click next step plus a menu for anything else
// ---------------------------------------------------------------------------
const repairStatusFlow = ['Pending', 'Diagnosis', 'In Progress', 'Ready for Pickup', 'Released'];

function StatusActions({ currentStatus, onChange }) {
  if (currentStatus === 'Released' || currentStatus === 'Cancelled') return null;
  const next = NEXT_STEP[currentStatus];
  const currentIdx = repairStatusFlow.indexOf(currentStatus);
  const others = [
    ...repairStatusFlow.slice(currentIdx + 1).filter((s) => s !== next?.status),
    'Cancelled',
  ];

  return (
    <div className="flex flex-col items-end gap-1.5 min-[1400px]:flex-row min-[1400px]:items-center min-[1400px]:justify-end min-[1400px]:gap-2">
      {next && (
        <button
          onClick={() => onChange(next.status)}
          className="px-3 py-1 text-xs font-semibold text-white bg-ink-800 hover:bg-ink-900 rounded-md whitespace-nowrap"
        >
          {next.label}
        </button>
      )}
      <select
        value=""
        onChange={(e) => e.target.value && onChange(e.target.value)}
        aria-label="Other status"
        className="w-20 px-2 py-1 text-xs border border-stone-300 rounded-md bg-white text-stone-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        <option value="" disabled>More…</option>
        {others.map((s) => (
          <option key={s} value={s}>{STATUS_LABELS[s] || s}</option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Repairs Page
// ---------------------------------------------------------------------------
export default function Repairs() {
  const [repairs, setRepairs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [stageFilter, setStageFilter] = useState('all');
  const [search, setSearch] = useState('');

  const fetchData = useCallback(async () => {
    setError('');
    try {
      const res = await api.get('/repairs');
      setRepairs(res.data);
    } catch (err) {
      setError('Failed to load repair requests.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const updateRepair = async (repairId, changes, failMessage) => {
    try {
      const res = await api.put(`/repairs/${repairId}`, changes);
      setRepairs((prev) => prev.map((r) => (r.id === repairId ? res.data : r)));
    } catch (err) {
      setError(errorMessage(err, failMessage));
    }
  };

  const deviceSuggestions = useMemo(
    () => [...new Set(repairs.map((r) => r.device_model).filter(Boolean))].sort(),
    [repairs],
  );

  const searched = useMemo(() => {
    const q = search.trim().toLowerCase().replace(/^#0*/, '');
    if (!q) return repairs;
    return repairs.filter((r) =>
      [r.customer_name, r.customer_phone, r.device_model, r.repair_type, r.issue_description, String(r.id)]
        .some((v) => (v || '').toLowerCase().includes(q)),
    );
  }, [repairs, search]);

  const stageCounts = searched.reduce((counts, r) => {
    const key = stageOf(r.status).key;
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
  const waitingCount = repairs.filter((r) => r.status === 'Ready for Pickup').length;

  const visible = searched.filter((r) => {
    if (stageFilter === 'all') return true;
    return stageOf(r.status).key === stageFilter;
  });

  const chipClass = (active) =>
    `inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
      active ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-stone-600 border-stone-200 hover:bg-stone-50'
    }`;

  return (
    <div className="lg:h-full lg:flex lg:flex-col">
      <div className="mb-5 flex-shrink-0">
        <h1 className="text-2xl text-stone-800">Repairs</h1>
        <p className="text-sm text-stone-500 mt-0.5">
          {loading ? 'Loading...' : `${waitingCount} waiting for pickup · ${repairs.length} total`}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)] min-[1400px]:grid-cols-[330px_minmax(0,1fr)] gap-6 lg:flex-1 lg:min-h-0">
        {/* Left box: add a repair */}
        <div className="lg:min-h-0 lg:overflow-y-auto">
          <QuickAddRepair deviceSuggestions={deviceSuggestions} onCreated={fetchData} />
        </div>

        {/* Right box: the list */}
        <div className="min-w-0 lg:min-h-0 lg:flex lg:flex-col">
          {error && (
            <div className="mb-4 flex-shrink-0 px-4 py-3 bg-brand-50 border border-brand-200 text-brand-800 text-sm rounded-lg flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => setError('')} className="text-brand-500 hover:text-brand-700 ml-2">&times;</button>
            </div>
          )}

          {/* Search and stage filter (the chips double as the color legend) */}
          <div className="mb-4 flex-shrink-0 flex flex-wrap items-center gap-2">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, phone, model or job #"
              className="w-full sm:w-64 px-3 py-2 border border-stone-300 rounded-md text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
            />
            <button onClick={() => setStageFilter('all')} className={chipClass(stageFilter === 'all')}>
              All <span className="opacity-60">{searched.length}</span>
            </button>
            {STAGES.map((stage) => (
              <button key={stage.key} onClick={() => setStageFilter(stage.key)} className={chipClass(stageFilter === stage.key)}>
                <span className={`h-2 w-2 rounded-full ${stage.dot}`} />
                {stage.label} <span className="opacity-60">{stageCounts[stage.key] || 0}</span>
              </button>
            ))}
          </div>

          {/* Table */}
          <div className="bg-white rounded-lg border border-stone-200 overflow-auto shadow-sm lg:flex-1 lg:min-h-0">
            {loading ? (
              <div className="p-8 space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 bg-stone-100 rounded animate-pulse" />
                ))}
              </div>
            ) : visible.length === 0 ? (
              <div className="text-center py-12 text-stone-500">
                <p className="text-lg font-medium">No repairs here</p>
                <p className="text-sm mt-1">
                  {search ? 'Nothing matches that search.' : repairs.length ? 'Nothing in this stage right now.' : 'Add the first one with the New repair form.'}
                </p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left [&>th]:sticky [&>th]:top-0 [&>th]:z-10 [&>th]:bg-stone-50 [&>th]:shadow-[inset_0_-1px_0_theme(colors.stone.200)]">
                    <th className="px-3 py-3 font-semibold text-stone-600">Job</th>
                    <th className="px-3 py-3 font-semibold text-stone-600">Customer &amp; phone</th>
                    <th className="px-3 py-3 font-semibold text-stone-600">Repair</th>
                    <th className="px-3 py-3 font-semibold text-stone-600">Status</th>
                    <th className="px-3 py-3 font-semibold text-stone-600 text-right">Update</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {visible.map((repair) => (
                    <tr key={repair.id} className="hover:bg-stone-50 transition-colors align-top">
                      <td className={`px-3 py-3 border-l-4 ${stageOf(repair.status).bar} whitespace-nowrap`}>
                        <div className="font-semibold text-stone-800 tabular-nums">{jobNumber(repair.id)}</div>
                        <div className="text-xs text-stone-500">{receivedLabel(repair.created_at || repair.updated_at)}</div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="font-medium text-stone-800">{repair.customer_name || `Customer #${repair.customer_id}`}</div>
                        {repair.customer_phone && <div className="text-xs text-stone-500 whitespace-nowrap">{repair.customer_phone}</div>}
                        <div className="text-xs font-semibold text-stone-700 mt-0.5">{repair.device_model}</div>
                      </td>
                      <td className="px-3 py-3 min-w-[120px] max-w-[260px]">
                        {repair.repair_type && <div className="font-medium text-stone-800">{repair.repair_type}</div>}
                        {repair.issue_description && <div className="text-xs text-stone-500 break-words">{repair.issue_description}</div>}
                      </td>
                      <td className="px-3 py-3">
                        <RepairStatusBadge status={repair.status} />
                        <div className="mt-1 flex items-center gap-2">
                          <InlineCost
                            value={repair.estimated_cost || 0}
                            onSave={(cost) => updateRepair(repair.id, { estimated_cost: cost }, 'Failed to update cost.')}
                          />
                          {repair.status !== 'Cancelled' && (
                            <PaidToggle
                              paid={repair.is_paid}
                              onChange={(isPaid) => updateRepair(repair.id, { is_paid: isPaid }, 'Failed to update payment.')}
                            />
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">
                        <StatusActions
                          currentStatus={repair.status}
                          onChange={(status) => updateRepair(repair.id, { status }, 'Failed to update repair status.')}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
