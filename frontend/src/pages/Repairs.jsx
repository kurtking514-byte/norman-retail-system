import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';

// What staff can pick in "What needs fixing"
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
  { key: 'done', label: 'Done', statuses: ['Ready for Pickup', 'Released', 'Completed'],
    badge: 'bg-terrace-100 text-terrace-800', bar: 'border-l-terrace-500', dot: 'bg-terrace-500' },
  { key: 'cancelled', label: 'Cancelled', statuses: ['Cancelled'],
    badge: 'bg-stone-100 text-stone-500', bar: 'border-l-stone-300', dot: 'bg-stone-400' },
];

const stageOf = (status) => STAGES.find((s) => s.statuses.includes(status)) || STAGES[0];

// Friendlier names for the stored status values
const STATUS_LABELS = {
  Pending: 'In line',
  Diagnosis: 'Checking the problem',
  'In Progress': 'Being repaired',
  'Ready for Pickup': 'Done – ready for pickup',
  Released: 'Released to customer',
  Cancelled: 'Cancelled',
};

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
// Customer search — type a name or phone number, pick from the matches
// ---------------------------------------------------------------------------
function CustomerPicker({ value, onChange }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (value) return undefined;
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.get('/customers', { params: { q: query, limit: 8 } });
        setResults(res.data);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query, value]);

  if (value) {
    return (
      <div className="flex items-center justify-between px-3 py-2 border border-brand-300 bg-brand-50 rounded-lg text-sm">
        <div>
          <div className="font-medium text-stone-800">{value.name || 'No name'}</div>
          <div className="text-xs text-stone-500">{value.phone_number}</div>
        </div>
        <button type="button" onClick={() => onChange(null)} className="text-xs font-medium text-brand-600 hover:underline">
          Change
        </button>
      </div>
    );
  }

  return (
    <div>
      <input
        autoFocus
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by name or phone number"
        className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
      />
      <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-stone-200 divide-y divide-stone-100">
        {results.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onChange(c)}
            className="w-full text-left px-3 py-2 hover:bg-stone-50"
          >
            <div className="text-sm font-medium text-stone-800">{c.name || 'No name'}</div>
            <div className="text-xs text-stone-500">{c.phone_number}</div>
          </button>
        ))}
        {!searching && results.length === 0 && (
          <p className="px-3 py-2 text-xs text-stone-400">
            No customer found. Choose "New Customer" to add them.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// New Repair Request Modal
// ---------------------------------------------------------------------------
const emptyForm = {
  customerMode: 'existing',
  customer: null,
  first_name: '',
  last_name: '',
  phone_number: '',
  device_model: '',
  repair_type: '',
  issue_description: '',
  estimated_cost: '',
};

function NewRepairModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(emptyForm);
      setError('');
      setSubmitting(false);
    }
  }, [open]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!form.device_model) {
      setError('Please fill in the device model.');
      return;
    }
    if (!form.repair_type && !form.issue_description.trim()) {
      setError('Choose what needs fixing or describe the issue.');
      return;
    }

    const body = {
      device_model: form.device_model,
      repair_type: form.repair_type || null,
      issue_description: form.issue_description,
      estimated_cost: parseFloat(form.estimated_cost) || 0,
    };

    if (form.customerMode === 'existing') {
      if (!form.customer) {
        setError('Please pick a customer.');
        return;
      }
      body.customer_id = form.customer.id;
    } else {
      if (!form.first_name || !form.last_name || !form.phone_number) {
        setError('Please fill in all customer fields.');
        return;
      }
      body.first_name = form.first_name;
      body.last_name = form.last_name;
      body.phone_number = form.phone_number;
    }

    setSubmitting(true);
    try {
      await api.post('/repairs', body);
      setForm(emptyForm);
      onCreated();
      onClose();
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to create repair request. Please try again.';
      if (data?.detail?.error?.message) {
        msg = data.detail.error.message;
      } else if (data?.error?.message) {
        msg = data.error.message;
      } else if (data?.detail) {
        msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-stone-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-stone-800">New Repair Request</h2>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
              {error}
            </div>
          )}

          {/* Device info */}
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">Device Model *</label>
            <input
              name="device_model"
              value={form.device_model}
              onChange={handleChange}
              placeholder="e.g. iPhone 15 Pro Max"
              className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">What needs fixing *</label>
            <select
              name="repair_type"
              value={form.repair_type}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="">Choose…</option>
              {REPAIR_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">
              Details {form.repair_type ? <span className="font-normal text-stone-400">(optional)</span> : '*'}
            </label>
            <textarea
              name="issue_description"
              rows="3"
              value={form.issue_description}
              onChange={handleChange}
              placeholder={form.repair_type === 'Other' ? 'Describe the problem...' : 'Anything else the technician should know...'}
              className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1">Estimated Cost</label>
            <div className="relative">
              <span className="absolute left-3 top-2.5 text-stone-500 text-sm">₱</span>
              <input
                name="estimated_cost"
                type="number"
                step="0.01"
                min="0"
                value={form.estimated_cost}
                onChange={handleChange}
                placeholder="0.00"
                className="w-full pl-8 pr-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>

          {/* Customer mode toggle */}
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">Customer</label>
            <div className="flex gap-4 mb-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="customerMode"
                  value="existing"
                  checked={form.customerMode === 'existing'}
                  onChange={handleChange}
                  className="text-brand-600"
                />
                Existing Customer
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="customerMode"
                  value="new"
                  checked={form.customerMode === 'new'}
                  onChange={handleChange}
                  className="text-brand-600"
                />
                New Customer
              </label>
            </div>

            {form.customerMode === 'existing' ? (
              <CustomerPicker
                value={form.customer}
                onChange={(customer) => setForm((prev) => ({ ...prev, customer }))}
              />
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-stone-700 mb-1">First Name *</label>
                  <input
                    name="first_name"
                    value={form.first_name}
                    onChange={handleChange}
                    className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-stone-700 mb-1">Last Name *</label>
                  <input
                    name="last_name"
                    value={form.last_name}
                    onChange={handleChange}
                    className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-stone-700 mb-1">Phone Number *</label>
                  <input
                    name="phone_number"
                    value={form.phone_number}
                    onChange={handleChange}
                    placeholder="+63-xxx-xxx-xxxx"
                    className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-stone-700 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className={`px-4 py-2 text-sm font-semibold text-white rounded-lg transition-colors ${
                submitting ? 'bg-brand-400 cursor-not-allowed' : 'bg-brand-600 hover:bg-brand-700'
              }`}
            >
              {submitting ? 'Creating...' : 'Create Repair Request'}
            </button>
          </div>
        </form>
      </div>
    </div>
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
      className="text-sm text-stone-700 hover:text-brand-600 hover:underline cursor-pointer text-left"
      title="Click to edit"
    >
      {peso.format(Number(value))}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Status update dropdown (used in table)
// ---------------------------------------------------------------------------
const repairStatusFlow = ['Pending', 'Diagnosis', 'In Progress', 'Ready for Pickup', 'Released'];

function RepairStatusDropdown({ currentStatus, onChange }) {
  const currentIdx = repairStatusFlow.indexOf(currentStatus);
  if (currentStatus === 'Released' || currentStatus === 'Cancelled') return null;

  const options = [];
  // Forward options
  for (let i = currentIdx + 1; i < repairStatusFlow.length; i++) {
    options.push(repairStatusFlow[i]);
  }
  // Cancel is available at any point (unless already cancelled or released)
  if (currentStatus !== 'Cancelled') {
    options.push('Cancelled');
  }

  const handleChange = (e) => {
    const newStatus = e.target.value;
    if (!newStatus) return;
    onChange(newStatus);
  };

  return (
    <select
      onChange={handleChange}
      defaultValue=""
      className="px-2 py-1 text-xs border border-stone-300 rounded-md focus:outline-none focus:ring-1 focus:ring-brand-500 bg-white"
    >
      <option value="" disabled>
        Change status...
      </option>
      {options.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s] || s}
        </option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Issue Cell — truncates long text, full text on click
// ---------------------------------------------------------------------------
function IssueCell({ text }) {
  const [expanded, setExpanded] = useState(false);
  const truncated = text && text.length > 60 ? text.slice(0, 60) + '...' : text;

  return (
    <div className="relative">
      <span
        className="text-stone-600 cursor-pointer hover:text-brand-600"
        onClick={() => setExpanded(!expanded)}
        title={expanded ? 'Click to collapse' : 'Click to view full text'}
      >
        {expanded ? text : truncated}
      </span>
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
  const [showModal, setShowModal] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
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

  const stageCounts = repairs.reduce((counts, r) => {
    const key = stageOf(r.status).key;
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
  const visible = stageFilter === 'all' ? repairs : repairs.filter((r) => stageOf(r.status).key === stageFilter);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (repairId, newStatus) => {
    try {
      await api.put(`/repairs/${repairId}`, { status: newStatus });
      fetchData();
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to update repair status.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    }
  };

  const handleCostSave = async (repairId, newCost) => {
    try {
      await api.put(`/repairs/${repairId}`, { estimated_cost: newCost });
      fetchData();
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to update cost.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-800">Repairs</h1>
          <p className="text-sm text-stone-500 mt-0.5">
            {loading ? 'Loading...' : `${repairs.length} repair${repairs.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          + New Repair Request
        </button>
      </div>

      {/* In-development notice */}
      <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg">
        <span className="font-semibold">In development:</span> repair tracking works, but
        photo-based damage assessment and AI repair quotes are still being built.
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 ml-2">&times;</button>
        </div>
      )}

      {/* Stage filter (doubles as the color legend) */}
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => setStageFilter('all')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
            stageFilter === 'all' ? 'bg-stone-800 text-white border-stone-800' : 'bg-white text-stone-600 border-stone-200 hover:bg-stone-50'
          }`}
        >
          All <span className="opacity-60">{repairs.length}</span>
        </button>
        {STAGES.map((stage) => (
          <button
            key={stage.key}
            onClick={() => setStageFilter(stage.key)}
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              stageFilter === stage.key ? `${stage.badge} border-transparent ring-2 ring-offset-1 ring-stone-300` : 'bg-white text-stone-600 border-stone-200 hover:bg-stone-50'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${stage.dot}`} />
            {stage.label} <span className="opacity-60">{stageCounts[stage.key] || 0}</span>
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-stone-200 overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-stone-100 rounded animate-pulse" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="text-center py-12 text-stone-500">
            <p className="text-lg font-medium">No repair requests found</p>
            <p className="text-sm mt-1">
              {repairs.length ? 'Nothing in this stage right now.' : 'Click "New Repair Request" to create one.'}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-3 font-semibold text-stone-600">Customer</th>
                <th className="text-left px-4 py-3 font-semibold text-stone-600">Device Model</th>
                <th className="text-left px-4 py-3 font-semibold text-stone-600">Repair</th>
                <th className="text-left px-4 py-3 font-semibold text-stone-600">Status</th>
                <th className="text-left px-4 py-3 font-semibold text-stone-600">Est. Cost</th>
                <th className="text-right px-4 py-3 font-semibold text-stone-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {visible.map((repair) => (
                <tr key={repair.id} className="hover:bg-stone-50 transition-colors">
                  <td className={`px-4 py-3 border-l-4 ${stageOf(repair.status).bar}`}>
                    <span className="font-medium text-stone-800">
                      {repair.customer_name || `Customer #${repair.customer_id}`}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-stone-700 font-medium">{repair.device_model}</td>
                  <td className="px-4 py-3 max-w-[260px]">
                    {repair.repair_type && (
                      <div className="font-medium text-stone-800">{repair.repair_type}</div>
                    )}
                    {repair.issue_description && <IssueCell text={repair.issue_description} />}
                  </td>
                  <td className="px-4 py-3">
                    <RepairStatusBadge status={repair.status} />
                  </td>
                  <td className="px-4 py-3">
                    <InlineCost
                      value={repair.estimated_cost || 0}
                      onSave={(newCost) => handleCostSave(repair.id, newCost)}
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <RepairStatusDropdown
                      currentStatus={repair.status}
                      onChange={(newStatus) => handleStatusChange(repair.id, newStatus)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* New Repair Modal */}
      <NewRepairModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onCreated={fetchData}
      />
    </div>
  );
}
