            import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import StatusBadge from '../components/common/StatusBadge';

/**
 * Inventory page — product table with search, add-product modal, and delete.
 *
 * NOTE: Brand/Category names aren't fetchable yet (no /brands or /categories
 * endpoints exist until later phases) — showing raw brand_id/category_id for now.
 * TODO: replace with brand/category name once endpoints exist.
 */

// ---------------------------------------------------------------------------
// Add Product Modal
// ---------------------------------------------------------------------------
const defaultForm = {
  name: '',
  model_number: '',
  brand_id: 1,
  category_id: 1,
  cost_price: '',
  selling_price: '',
  warranty_months: 12,
  description: '',
};

function AddProductModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState(defaultForm);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const cost = parseFloat(form.cost_price);
    const selling = parseFloat(form.selling_price);

    // Client-side validation: selling_price must be > cost_price
    if (isNaN(cost) || isNaN(selling)) {
      setError('Please enter valid prices.');
      return;
    }
    if (selling <= cost) {
      setError('Selling price must be greater than cost price.');
      return;
    }

    setSubmitting(true);
    try {
      await api.post('/products', {
        name: form.name,
        model_number: form.model_number,
        brand_id: parseInt(form.brand_id, 10),
        category_id: parseInt(form.category_id, 10),
        cost_price: cost,
        selling_price: selling,
        warranty_months: parseInt(form.warranty_months, 10) || 12,
        description: form.description || null,
      });
      setForm(defaultForm);
      onCreated();
      onClose();
    } catch (err) {
      const data = err.response?.data;
      if (data?.error?.message) {
        setError(data.error.message);
      } else if (data?.detail?.error?.message) {
        setError(data.detail.error.message);
      } else {
        setError('Failed to create product. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800">Add Product</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Name *</label>
              <input name="name" value={form.name} onChange={handleChange} required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Model Number *</label>
              <input name="model_number" value={form.model_number} onChange={handleChange} required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Brand ID *</label>
              <input name="brand_id" type="number" value={form.brand_id} onChange={handleChange} required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Category ID *</label>
              <input name="category_id" type="number" value={form.category_id} onChange={handleChange} required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Cost Price *</label>
              <input name="cost_price" type="number" step="0.01" value={form.cost_price} onChange={handleChange} required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Selling Price *</label>
              <input name="selling_price" type="number" step="0.01" value={form.selling_price} onChange={handleChange} required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Warranty (months)</label>
              <input name="warranty_months" type="number" value={form.warranty_months} onChange={handleChange}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div></div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
              <textarea name="description" rows="3" value={form.description} onChange={handleChange}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={submitting}
              className={`px-4 py-2 text-sm font-semibold text-white rounded-lg transition-colors ${
                submitting ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
              }`}>
              {submitting ? 'Saving...' : 'Add Product'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock Badge (delegated to shared StatusBadge)
// ---------------------------------------------------------------------------
// Main Inventory Page
// ---------------------------------------------------------------------------
export default function Inventory() {
  const [products, setProducts] = useState([]);
  const [inventoryMap, setInventoryMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const debounceRef = useRef(null);

  // Debounce search input — 300ms
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      // Fetch products with search query if debouncedSearch is set
      const params = {};
      if (debouncedSearch.trim()) {
        params.q = debouncedSearch.trim();
      }
      const productsRes = await api.get('/products', { params });

      // Fetch all inventory once and group by product_id (efficient approach)
      const inventoryRes = await api.get('/inventory');
      const stockCounts = {};
      for (const item of inventoryRes.data) {
        const pid = item.product_id;
        if (!stockCounts[pid]) stockCounts[pid] = 0;
        if (item.status === 'In Stock') stockCounts[pid] += 1;
      }

      setProducts(productsRes.data);
      setInventoryMap(stockCounts);
    } catch (err) {
      setError('Failed to load products.');
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (productId) => {
    if (!window.confirm('Are you sure you want to delete this product?')) return;
    setDeletingId(productId);
    try {
      await api.delete(`/products/${productId}`);
      setProducts((prev) => prev.map((p) => (p.id === productId ? { ...p, is_active: false } : p)));
    } catch (err) {
      setError('Failed to delete product.');
    } finally {
      setDeletingId(null);
    }
  };

  const totalStockCount = Object.values(inventoryMap).reduce((sum, c) => sum + c, 0);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Inventory</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {loading ? 'Loading...' : `${products.length} products \u00B7 ${totalStockCount} units in stock`}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          + Add Product
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 ml-2">&times;</button>
        </div>
      )}

      {/* Search */}
      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or model number..."
          className="w-full max-w-md px-4 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-slate-100 rounded animate-pulse" />
            ))}
          </div>
        ) : products.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            <p className="text-lg font-medium">No products found</p>
            <p className="text-sm mt-1">
              {debouncedSearch ? 'Try a different search term.' : 'Click "Add Product" to get started.'}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Brand ID</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Category ID</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Selling Price</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Stock</th>
                <th className="text-right px-4 py-3 font-semibold text-slate-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {products.map((product) => {
                const stockCount = inventoryMap[product.id] || 0;
                return (
                  <tr
                    key={product.id}
                    className={`hover:bg-slate-50 transition-colors ${
                      !product.is_active ? 'opacity-40 pointer-events-none' : ''
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-800">{product.name}</div>
                      <div className="text-xs text-slate-400">{product.model_number}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{product.brand_id}</td>
                    <td className="px-4 py-3 text-slate-600">{product.category_id}</td>
                    <td className="px-4 py-3 text-slate-600">${Number(product.selling_price).toFixed(2)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge count={stockCount} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        disabled
                        className="px-3 py-1.5 text-xs font-medium text-slate-400 bg-slate-100 rounded mr-2 cursor-not-allowed"
                        title="Edit coming in a later phase"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(product.id)}
                        disabled={deletingId === product.id || !product.is_active}
                        className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                          !product.is_active
                            ? 'text-slate-400 bg-slate-100 cursor-not-allowed'
                            : deletingId === product.id
                            ? 'text-red-400 bg-red-50 cursor-not-allowed'
                            : 'text-red-600 bg-red-50 hover:bg-red-100'
                        }`}
                      >
                        {deletingId === product.id ? 'Deleting...' : product.is_active ? 'Delete' : 'Deleted'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Product Modal */}
      <AddProductModal open={showModal} onClose={() => setShowModal(false)} onCreated={fetchData} />
    </div>
  );
}
