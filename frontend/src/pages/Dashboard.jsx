import { useState, useEffect } from 'react';
import api from '../services/api';

/**
 * Dashboard page — fetches product and inventory data to compute stat cards.
 *
 * NOTE: This uses client-side computation by calling GET /api/v1/products and
 * GET /api/v1/inventory separately and deriving counts. Once the real
 * /api/v1/dashboard/stats endpoint is built in Phase 7, replace these two API
 * calls with a single call to that endpoint.
 */

function StatCard({ title, value, loading, color }) {
  const colorClasses = {
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    green: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    red: 'bg-red-50 border-red-200 text-red-700',
  };

  return (
    <div className={`rounded-xl border p-5 ${colorClasses[color] || colorClasses.blue}`}>
      <p className="text-sm font-medium opacity-80">{title}</p>
      {loading ? (
        <div className="mt-2 h-8 w-20 bg-current opacity-20 rounded animate-pulse" />
      ) : (
        <p className="mt-1 text-3xl font-bold">{value ?? '—'}</p>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState({ totalProducts: 0, inStockCount: 0, outOfStockCount: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      setLoading(true);
      setError('');
      try {
        const [productsRes, inventoryRes] = await Promise.all([
          api.get('/products'),
          api.get('/inventory'),
        ]);

        if (cancelled) return;

        const products = productsRes.data;
        const inventoryItems = inventoryRes.data;

        // Group inventory by product_id and count statuses
        const inStockCount = inventoryItems.filter(
          (item) => item.status === 'In Stock',
        ).length;
        const outOfStockCount = inventoryItems.filter(
          (item) =>
            item.status === 'Sold' ||
            item.status === 'Reserved' ||
            item.status === 'In Repair',
        ).length;

        setStats({
          totalProducts: products.length,
          inStockCount,
          outOfStockCount,
        });
      } catch (err) {
        if (!cancelled) {
          setError('Failed to load dashboard data.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchStats();
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-red-600 font-medium">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 text-sm text-blue-600 hover:underline"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard title="Total Products" value={stats.totalProducts} loading={loading} color="blue" />
        <StatCard title="In Stock" value={stats.inStockCount} loading={loading} color="green" />
        <StatCard title="Out of Stock / Reserved" value={stats.outOfStockCount} loading={loading} color="red" />
      </div>

      {/* Empty state */}
      {!loading && stats.totalProducts === 0 && (
        <div className="mt-8 text-center py-12 bg-white rounded-xl border border-slate-200">
          <div className="text-4xl mb-3">📦</div>
          <h3 className="text-lg font-semibold text-slate-700">No Products Yet</h3>
          <p className="text-sm text-slate-500 mt-1">
            Head over to the Inventory page to add your first product.
          </p>
        </div>
      )}
    </div>
  );
}

