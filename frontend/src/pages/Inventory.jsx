import { useState, useEffect, useCallback, useMemo } from 'react';
import api from '../services/api';
import StatusBadge from '../components/common/StatusBadge';
import ImportProductsModal from '../components/inventory/ImportProductsModal';
import ProductPanel from '../components/inventory/ProductPanel';

/**
 * Inventory page — every product with brand/category names, category tabs,
 * brand/stock filters and search. Clicking a product opens a side panel to
 * view and edit its details, specs and stock.
 *
 * The full product list (up to 1000) is loaded once and filtered in the
 * browser so tabs and search respond instantly.
 */

const LOW_STOCK = 3;

const peso = new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
  maximumFractionDigits: 2,
});

const STOCK_FILTERS = [
  { value: 'all', label: 'Any stock' },
  { value: 'in', label: 'In stock' },
  { value: 'low', label: `Low (${LOW_STOCK} or fewer)` },
  { value: 'out', label: 'Out of stock' },
];

function matchesStock(count, filter) {
  if (filter === 'in') return count > 0;
  if (filter === 'low') return count > 0 && count <= LOW_STOCK;
  if (filter === 'out') return count === 0;
  return true;
}

export default function Inventory() {
  const [products, setProducts] = useState([]);
  const [stock, setStock] = useState({});
  const [brands, setBrands] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [categoryTab, setCategoryTab] = useState('all');
  const [brandFilter, setBrandFilter] = useState('all');
  const [stockFilter, setStockFilter] = useState('all');
  const [showHidden, setShowHidden] = useState(false);
  const [search, setSearch] = useState('');

  const [panel, setPanel] = useState(null); // null | { product } (product null = new)
  const [showImport, setShowImport] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const fetchData = useCallback(async () => {
    setError('');
    try {
      const [productsRes, stockRes, brandsRes, categoriesRes] = await Promise.all([
        api.get('/products'),
        api.get('/inventory/summary'),
        api.get('/brands'),
        api.get('/categories'),
      ]);
      setProducts(productsRes.data);
      setStock(stockRes.data);
      setBrands(brandsRes.data);
      setCategories(categoriesRes.data);
    } catch (err) {
      setError('Failed to load products.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const brandName = useMemo(() => Object.fromEntries(brands.map((b) => [b.id, b.name])), [brands]);
  const categoryName = useMemo(
    () => Object.fromEntries(categories.map((c) => [c.id, c.name])),
    [categories],
  );
  const stockOf = (p) => stock[p.id] || 0;

  // Everything except the category tab, so tab counts reflect the other filters
  const baseFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products.filter((p) => {
      if (!showHidden && p.is_active === false) return false;
      if (brandFilter !== 'all' && String(p.brand_id) !== brandFilter) return false;
      if (!matchesStock(stock[p.id] || 0, stockFilter)) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        p.model_number.toLowerCase().includes(q) ||
        (brandName[p.brand_id] || '').toLowerCase().includes(q)
      );
    });
  }, [products, stock, search, brandFilter, stockFilter, showHidden, brandName]);

  const tabCounts = useMemo(() => {
    const counts = {};
    baseFiltered.forEach((p) => {
      counts[p.category_id] = (counts[p.category_id] || 0) + 1;
    });
    return counts;
  }, [baseFiltered]);

  const visible = useMemo(
    () =>
      baseFiltered
        .filter((p) => categoryTab === 'all' || String(p.category_id) === categoryTab)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [baseFiltered, categoryTab],
  );

  const totalUnits = Object.values(stock).reduce((sum, c) => sum + c, 0);
  const activeCount = products.filter((p) => p.is_active !== false).length;
  const filtersOn = search || brandFilter !== 'all' || stockFilter !== 'all' || showHidden;

  const setVisibility = async (product, isActive) => {
    if (!isActive && !window.confirm(`Hide "${product.name}"? It won't be offered by the chatbot until you show it again.`)) {
      return;
    }
    setBusyId(product.id);
    try {
      if (isActive) {
        await api.put(`/products/${product.id}`, { is_active: true });
      } else {
        await api.delete(`/products/${product.id}`);
      }
      setProducts((prev) => prev.map((p) => (p.id === product.id ? { ...p, is_active: isActive } : p)));
    } catch (err) {
      setError(`Failed to ${isActive ? 'show' : 'hide'} product.`);
    } finally {
      setBusyId(null);
    }
  };

  const clearFilters = () => {
    setSearch('');
    setBrandFilter('all');
    setStockFilter('all');
    setShowHidden(false);
  };

  const tabClass = (active) =>
    `px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
      active ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
    }`;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between gap-4 mb-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Inventory</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {loading ? 'Loading...' : `${activeCount} products · ${totalUnits} units in stock`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowImport(true)}
            className="px-4 py-2.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-sm font-semibold rounded-lg transition-colors shadow-sm"
          >
            Import spreadsheet
          </button>
          <button
            onClick={() => setPanel({ product: null })}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
          >
            + Add Product
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 ml-2">&times;</button>
        </div>
      )}

      {/* Category tabs */}
      <div className="flex gap-2 overflow-x-auto pb-1 mb-3">
        <button className={tabClass(categoryTab === 'all')} onClick={() => setCategoryTab('all')}>
          All <span className="opacity-60">{baseFiltered.length}</span>
        </button>
        {categories.map((c) => (
          <button
            key={c.id}
            className={tabClass(categoryTab === String(c.id))}
            onClick={() => setCategoryTab(String(c.id))}
          >
            {c.name} <span className="opacity-60">{tabCounts[c.id] || 0}</span>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, model number or brand..."
          className="w-full max-w-sm px-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={brandFilter}
          onChange={(e) => setBrandFilter(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
        >
          <option value="all">All brands</option>
          {brands.map((b) => (
            <option key={b.id} value={String(b.id)}>{b.name}</option>
          ))}
        </select>
        <select
          value={stockFilter}
          onChange={(e) => setStockFilter(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
        >
          {STOCK_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />
          Show hidden
        </label>
        {filtersOn && (
          <button onClick={clearFilters} className="text-sm text-blue-600 hover:underline">
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-slate-100 rounded animate-pulse" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            <p className="text-lg font-medium">No products found</p>
            <p className="text-sm mt-1">
              {products.length === 0
                ? 'Click "Add Product" or "Import spreadsheet" to get started.'
                : 'Try a different search, tab or filter.'}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Product</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Brand</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Category</th>
                <th className="text-right px-4 py-3 font-semibold text-slate-600">Price</th>
                <th className="text-left px-4 py-3 font-semibold text-slate-600">Stock</th>
                <th className="text-right px-4 py-3 font-semibold text-slate-600">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visible.map((product) => {
                const hidden = product.is_active === false;
                const specs = Object.values(product.specifications || {}).slice(0, 3).join(' · ');
                return (
                  <tr
                    key={product.id}
                    onClick={() => setPanel({ product })}
                    className={`cursor-pointer hover:bg-slate-50 transition-colors ${hidden ? 'opacity-50' : ''}`}
                  >
                    <td className="px-4 py-3 max-w-xs">
                      <div className="font-medium text-slate-800 truncate">
                        {product.name}
                        {hidden && <span className="ml-2 text-xs font-normal text-slate-500">(hidden)</span>}
                      </div>
                      <div className="text-xs text-slate-400 truncate">
                        {product.model_number}
                        {specs && <span className="text-slate-400"> · {specs}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{brandName[product.brand_id] || '—'}</td>
                    <td className="px-4 py-3 text-slate-600">{categoryName[product.category_id] || '—'}</td>
                    <td className="px-4 py-3 text-right text-slate-700 tabular-nums">
                      {peso.format(Number(product.selling_price))}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge count={stockOf(product)} />
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setPanel({ product })}
                        className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded mr-2"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setVisibility(product, hidden)}
                        disabled={busyId === product.id}
                        className={`px-3 py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50 ${
                          hidden
                            ? 'text-emerald-700 bg-emerald-50 hover:bg-emerald-100'
                            : 'text-red-600 bg-red-50 hover:bg-red-100'
                        }`}
                      >
                        {hidden ? 'Show' : 'Hide'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <ProductPanel
        open={panel !== null}
        product={panel?.product || null}
        stock={panel?.product ? stockOf(panel.product) : 0}
        brands={brands}
        categories={categories}
        onClose={() => setPanel(null)}
        onSaved={fetchData}
        onBrandCreated={(b) => setBrands((prev) => [...prev, b].sort((x, y) => x.name.localeCompare(y.name)))}
        onCategoryCreated={(c) => setCategories((prev) => [...prev, c].sort((x, y) => x.name.localeCompare(y.name)))}
      />
      <ImportProductsModal open={showImport} onClose={() => setShowImport(false)} onImported={fetchData} />
    </div>
  );
}
