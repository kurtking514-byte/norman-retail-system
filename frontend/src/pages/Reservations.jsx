import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import StatusBadge from '../components/common/StatusBadge';

// ---------------------------------------------------------------------------
// New Reservation Modal
// ---------------------------------------------------------------------------
const emptyForm = {
  customerMode: 'existing', // 'existing' | 'new'
  customer_id: '',
  first_name: '',
  last_name: '',
  phone_number: '',
  product_id: '',
};

function NewReservationModal({ open, onClose, onCreated, products }) {
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [search, setSearch] = useState('');

  // Reset form when modal opens
  useEffect(() => {
    if (open) {
      setForm(emptyForm);
      setError('');
      setSearch('');
      setSubmitting(false);
    }
  }, [open]);

  const filteredProducts = products.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.model_number.toLowerCase().includes(search.toLowerCase()),
  );

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!form.product_id) {
      setError('Please select a product.');
      return;
    }

    const body = {
      product_id: parseInt(form.product_id, 10),
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
      await api.post('/reservations', body);
      setForm(emptyForm);
      onCreated();
      onClose();
    } catch (err) {
      const data = err.response?.data;
      // Parse the standard error shape
      let msg = 'Failed to create reservation. Please try again.';
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
          <h2 className="text-lg font-semibold text-slate-800">New Reservation</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
              {error}
            </div>
          )}

          {/* Product search / select */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Product *</label>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search products..."
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-2"
            />
            <select
              name="product_id"
              value={form.product_id}
              onChange={handleChange}
              required
              size={4}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">-- Select a product --</option>
              {filteredProducts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.model_number}) — ${Number(p.selling_price).toFixed(2)}
                </option>
              ))}
            </select>
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
              {submitting ? 'Creating...' : 'Create Reservation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit Status Dropdown (used in table)
// ---------------------------------------------------------------------------
function StatusDropdown({ currentStatus, onChange }) {
  const allowedTransitions = {
    Pending: ['Confirmed', 'Cancelled'],
    Confirmed: ['Claimed', 'Cancelled'],
    Claimed: [],
    Cancelled: [],
  };

  const options = allowedTransitions[currentStatus] || [];

  if (options.length === 0) return null;

  const handleChange = (e) => {
    const newStatus = e.target.value;
    if (!newStatus) return;

    // Show confirm dialog for actions with inventory side-effects
    if (newStatus === 'Claimed') {
      if (!window.confirm('Marking as Claimed will mark this unit as sold. Continue?')) {
        // Reset select to default
        e.target.value = '';
        return;
      }
    }
    if (newStatus === 'Cancelled') {
      if (!window.confirm('Cancelling this reservation will release the held inventory back to stock. Continue?')) {
        e.target.value = '';
        return;
      }
    }

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
// Reservations Page
// ---------------------------------------------------------------------------
export default function Reservations() {
  const [reservations, setReservations] = useState([]);
  const [products, setProducts] = useState([]);
  const [productMap, setProductMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showModal, setShowModal] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      // Fetch products for lookup map
      const productsRes = await api.get('/products');
      const pList = productsRes.data;
      setProducts(pList);
      const pMap = {};
      for (const p of pList) {
        pMap[p.id] = p;
      }
      setProductMap(pMap);

      // Fetch reservations
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const reservationsRes = await api.get('/reservations', { params });
      setReservations(reservationsRes.data);
    } catch (err) {
      setError('Failed to load reservations.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (reservationId, newStatus) => {
    try {
      await api.put(`/reservations/${reservationId}`, { status: newStatus });
      // Refresh data
      fetchData();
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to update reservation.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Reservations</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {loading ? 'Loading...' : `${reservations.length} reservation${reservations.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          + New Reservation
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
          <option value="Confirmed">Confirmed</option>
          <option value="Claimed">Claimed</option>
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
        ) : reservations.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            <p className="text-lg font-medium">No reservations found</p>
            <p className="text-sm mt-1">
              {statusFilter ? 'Try a different filter.' : 'Click "New Reservation" to create one.'}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Customer</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Product</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Reservation Date</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Expiry Date</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Status</th>
                <th className="text-right px-4 py-3 font-semibold text-slate-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {reservations.map((res) => {
                const product = productMap[res.product_id];
                return (
                  <tr key={res.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      {/* TODO: Display real customer name once /customers endpoint exists.
                          For now, show Customer #ID since the API only returns customer_id. */}
                      <span className="font-medium text-slate-800">
                        Customer #{res.customer_id}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {product ? (
                        <>
                          <div className="font-medium text-slate-800">{product.name}</div>
                          <div className="text-xs text-slate-400">{product.model_number}</div>
                        </>
                      ) : (
                        <span className="text-slate-400">Product #{res.product_id}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(res.reservation_date)}</td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(res.expiry_date)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={res.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <StatusDropdown
                        currentStatus={res.status}
                        onChange={(newStatus) => handleStatusChange(res.id, newStatus)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* New Reservation Modal */}
      <NewReservationModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onCreated={fetchData}
        products={products}
      />
    </div>
  );
}
