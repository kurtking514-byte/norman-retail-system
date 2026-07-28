import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import StatusBadge from '../components/common/StatusBadge';

// ---------------------------------------------------------------------------
// New Repair Request Modal
// ---------------------------------------------------------------------------
const emptyForm = {
  customerMode: 'existing',
  customer_id: '',
  first_name: '',
  last_name: '',
  phone_number: '',
  device_model: '',
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

    if (!form.device_model || !form.issue_description) {
      setError('Please fill in device model and issue description.');
      return;
    }

    const body = {
      device_model: form.device_model,
      issue_description: form.issue_description,
      estimated_cost: parseFloat(form.estimated_cost) || 0,
    };

    if (form.customerMode === 'existing') {
      if (!form.customer_id) {
        setError('Please enter a Customer ID.');
        return;
      }
      body.customer_id = parseInt(form.customer_id, 10);
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
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">New Repair Request</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
              {error}
            </div>
          )}

          {/* Device info */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Device Model *</label>
            <input
              name="device_model"
              value={form.device_model}
              onChange={handleChange}
              placeholder="e.g. iPhone 15 Pro Max"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Issue Description *</label>
            <textarea
              name="issue_description"
              rows="3"
              value={form.issue_description}
              onChange={handleChange}
              placeholder="Describe the problem..."
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Estimated Cost</label>
            <div className="relative">
              <span className="absolute left-3 top-2.5 text-slate-500 text-sm">$</span>
              <input
                name="estimated_cost"
                type="number"
                step="0.01"
                min="0"
                value={form.estimated_cost}
                onChange={handleChange}
                placeholder="0.00"
                className="w-full pl-8 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Customer mode toggle */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">Customer</label>
            <div className="flex gap-4 mb-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="customerMode"
                  value="existing"
                  checked={form.customerMode === 'existing'}
                  onChange={handleChange}
                  className="text-blue-600"
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
                  className="text-blue-600"
                />
                New Customer
              </label>
            </div>

            {form.customerMode === 'existing' ? (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Customer ID *</label>
                <input
                  name="customer_id"
                  type="number"
                  value={form.customer_id}
                  onChange={handleChange}
                  placeholder="Enter customer ID"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-slate-400 mt-1">
                  {/* TODO: Replace with customer search when /customers endpoint exists */}
                  Enter the numeric customer ID from the database.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">First Name *</label>
                  <input
                    name="first_name"
                    value={form.first_name}
                    onChange={handleChange}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Last Name *</label>
                  <input
                    name="last_name"
                    value={form.last_name}
                    onChange={handleChange}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-slate-700 mb-1">Phone Number *</label>
                  <input
                    name="phone_number"
                    value={form.phone_number}
                    onChange={handleChange}
                    placeholder="+63-xxx-xxx-xxxx"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className={`px-4 py-2 text-sm font-semibold text-white rounded-lg transition-colors ${
                submitting ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
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
        <span className="absolute left-2 text-slate-500 text-xs">$</span>
        <input
          type="number"
          step="0.01"
          min="0"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={handleSave}
          onKeyDown={handleKeyDown}
          autoFocus
          className="w-24 pl-5 pr-2 py-1 text-xs border border-blue-400 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className="text-sm text-slate-700 hover:text-blue-600 hover:underline cursor-pointer text-left"
      title="Click to edit"
    >
      ${Number(value).toFixed(2)}
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
      className="px-2 py-1 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
    >
      <option value="" disabled>
        Change status...
      </option>
      {options.map((s) => (
        <option key={s} value={s}>
          {s}
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
        className="text-slate-600 cursor-pointer hover:text-blue-600"
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
  const [statusFilter, setStatusFilter] = useState('');
  const [showModal, setShowModal] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const res = await api.get('/repairs', { params });
      setRepairs(res.data);
    } catch (err) {
      setError('Failed to load repair requests.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

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
          <h1 className="text-2xl font-bold text-slate-800">Repairs</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {loading ? 'Loading...' : `${repairs.length} repair${repairs.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          + New Repair Request
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 ml-2">&times;</button>
        </div>
      )}

      {/* Filter */}
      <div className="mb-4 flex items-center gap-2">
        <label className="text-sm text-slate-600 font-medium">Status:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">All</option>
          <option value="Pending">Pending</option>
          <option value="Diagnosis">Diagnosis</option>
          <option value="In Progress">In Progress</option>
          <option value="Ready for Pickup">Ready for Pickup</option>
          <option value="Released">Released</option>
          <option value="Cancelled">Cancelled</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-slate-100 rounded animate-pulse" />
            ))}
          </div>
        ) : repairs.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            <p className="text-lg font-medium">No repair requests found</p>
            <p className="text-sm mt-1">
              {statusFilter ? 'Try a different filter.' : 'Click "New Repair Request" to create one.'}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Customer</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Device Model</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Issue</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Status</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Est. Cost</th>
                <th className="text-right px-4 py-3 font-semibold text-slate-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {repairs.map((repair) => (
                <tr key={repair.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-medium text-slate-800">
                      Customer #{repair.customer_id}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700 font-medium">{repair.device_model}</td>
                  <td className="px-4 py-3 max-w-[240px]">
                    <IssueCell text={repair.issue_description} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={repair.status} />
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
