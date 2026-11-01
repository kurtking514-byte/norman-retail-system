import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { parseServerDate } from '../utils/dates';
import StatusBadge from '../components/common/StatusBadge';

/**
 * Dashboard page — an at-a-glance overview of what needs staff attention
 * today, built client-side from the existing list endpoints.
 *
 * Each endpoint is fetched independently (Promise.allSettled) so one failing
 * section doesn't blank the whole page.
 */

const ACTIVE_RESERVATION_STATUSES = ['Pending', 'Confirmed'];
const CLOSED_REPAIR_STATUSES = ['Released', 'Cancelled'];
const LOW_STOCK_THRESHOLD = 1;

const peso = new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
  maximumFractionDigits: 0,
});

function timeAgo(iso) {
  if (!iso) return '';
  const minutes = Math.round((Date.now() - parseServerDate(iso).getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

function AttentionCard({ to, label, value, hint, tone, loading }) {
  const tones = {
    red: 'border-red-200 bg-red-50 text-red-700',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    blue: 'border-blue-200 bg-blue-50 text-blue-700',
    calm: 'border-slate-200 bg-white text-slate-700',
  };
  const active = !loading && value > 0;
  return (
    <Link
      to={to}
      className={`rounded-xl border p-4 transition-shadow hover:shadow-md ${
        active ? tones[tone] : tones.calm
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide opacity-80">{label}</p>
      {loading ? (
        <div className="mt-2 h-8 w-12 rounded bg-slate-200 animate-pulse" />
      ) : (
        <p className="mt-1 text-3xl font-bold">{value ?? '—'}</p>
      )}
      <p className="mt-1 text-xs opacity-70">{hint}</p>
    </Link>
  );
}

function StatTile({ label, value, sub, loading }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      {loading ? (
        <div className="mt-2 h-7 w-24 rounded bg-slate-100 animate-pulse" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-slate-800 tabular-nums">{value ?? '—'}</p>
      )}
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

function Panel({ title, linkTo, linkLabel, children }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white flex flex-col min-w-0">
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
        {linkTo && (
          <Link to={linkTo} className="text-xs font-medium text-blue-600 hover:underline">
            {linkLabel}
          </Link>
        )}
      </div>
      <div className="flex-1">{children}</div>
    </section>
  );
}

function PanelMessage({ children }) {
  return <p className="px-5 py-8 text-center text-sm text-slate-400">{children}</p>;
}

function PanelSkeleton() {
  return (
    <div className="p-5 space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-10 rounded bg-slate-100 animate-pulse" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const endpoints = ['products', 'inventory', 'reservations', 'repairs', 'conversations', 'notifications'];
    const results = await Promise.allSettled(endpoints.map((e) => api.get(`/${e}`)));
    const next = {};
    const failedNames = [];
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') next[endpoints[i]] = r.value.data;
      else failedNames.push(endpoints[i]);
    });
    setData(next);
    setFailed(failedNames);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const products = data?.products ?? [];
  const inventory = data?.inventory ?? [];
  const reservations = data?.reservations ?? [];
  const repairs = data?.repairs ?? [];
  const conversations = data?.conversations ?? [];
  const notifications = data?.notifications ?? [];

  // ---- Derived numbers ------------------------------------------------------
  const productById = Object.fromEntries(products.map((p) => [p.id, p]));
  const inStock = inventory.filter((i) => i.status === 'In Stock');
  const inStockByProduct = {};
  inStock.forEach((i) => {
    inStockByProduct[i.product_id] = (inStockByProduct[i.product_id] || 0) + 1;
  });
  const stockValue = inStock.reduce(
    (sum, i) => sum + Number(productById[i.product_id]?.selling_price || 0),
    0,
  );
  const lowStock = products
    .filter((p) => p.is_active !== false)
    .map((p) => ({ ...p, count: inStockByProduct[p.id] || 0 }))
    .filter((p) => p.count <= LOW_STOCK_THRESHOLD)
    .sort((a, b) => a.count - b.count);

  const activeReservations = reservations.filter((r) =>
    ACTIVE_RESERVATION_STATUSES.includes(r.status),
  );
  const in24h = Date.now() + 24 * 60 * 60 * 1000;
  const expiringSoon = activeReservations.filter(
    (r) => parseServerDate(r.expiry_date).getTime() <= in24h,
  );
  const openRepairs = repairs.filter((r) => !CLOSED_REPAIR_STATUSES.includes(r.status));
  const readyForPickup = repairs.filter((r) => r.status === 'Ready for Pickup');
  const humanThreads = conversations.filter((c) => c.thread_state === 'HUMAN_CONTROLLED');

  const recentChats = [...conversations]
    .sort((a, b) => parseServerDate(b.last_message_timestamp) - parseServerDate(a.last_message_timestamp))
    .slice(0, 5);
  const upcomingReservations = [...activeReservations]
    .sort((a, b) => parseServerDate(a.expiry_date) - parseServerDate(b.expiry_date))
    .slice(0, 5);

  const today = new Date().toLocaleDateString('en-PH', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  return (
    <div className="max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">{today}</p>
          <h1 className="text-2xl font-bold text-slate-800">{greeting()}</h1>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-sm text-slate-500 hover:text-blue-600 disabled:text-slate-300"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {failed.length > 0 && (
        <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
          Couldn&apos;t load: {failed.join(', ')}. Some numbers below may be incomplete.
        </div>
      )}

      {/* Needs attention */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
          Needs attention
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <AttentionCard
            to="/live-chat"
            label="Chat handoffs"
            value={notifications.length}
            hint={`${humanThreads.length} chat${humanThreads.length !== 1 ? 's' : ''} handled by staff`}
            tone="red"
            loading={loading}
          />
          <AttentionCard
            to="/reservations"
            label="Expiring in 24h"
            value={expiringSoon.length}
            hint={`${activeReservations.length} active reservation${activeReservations.length !== 1 ? 's' : ''}`}
            tone="amber"
            loading={loading}
          />
          <AttentionCard
            to="/repairs"
            label="Open repairs"
            value={openRepairs.length}
            hint={`${readyForPickup.length} ready for pickup`}
            tone="blue"
            loading={loading}
          />
          <AttentionCard
            to="/inventory"
            label="Low / out of stock"
            value={lowStock.length}
            hint={`Products with ${LOW_STOCK_THRESHOLD} or fewer units`}
            tone="amber"
            loading={loading}
          />
        </div>
      </div>

      {/* Inventory snapshot */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatTile label="Units in stock" value={inStock.length} sub={`${products.length} products listed`} loading={loading} />
        <StatTile label="Stock value (selling price)" value={peso.format(stockValue)} loading={loading} />
        <StatTile
          label="Units sold / reserved"
          value={inventory.filter((i) => i.status === 'Sold' || i.status === 'Reserved').length}
          sub="All time"
          loading={loading}
        />
      </div>

      {/* Lists */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel title="Recent conversations" linkTo="/live-chat" linkLabel="Open Live Chat →">
          {loading ? (
            <PanelSkeleton />
          ) : recentChats.length === 0 ? (
            <PanelMessage>No customer messages yet.</PanelMessage>
          ) : (
            <ul className="divide-y divide-slate-100">
              {recentChats.map((c) => (
                <li key={c.messenger_user_id}>
                  <Link to="/live-chat" className="flex items-start gap-3 px-5 py-3 hover:bg-slate-50">
                    <span
                      className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${
                        c.unread_handoff ? 'bg-amber-500' : 'bg-transparent'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium text-slate-800">
                          {c.customer_name || 'Messenger user'}
                        </span>
                        <span className="flex-shrink-0 text-xs text-slate-400">
                          {timeAgo(c.last_message_timestamp)}
                        </span>
                      </div>
                      <p className="truncate text-sm text-slate-500">{c.last_message_text}</p>
                    </div>
                    <span
                      className={`flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        c.thread_state === 'HUMAN_CONTROLLED'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {c.thread_state === 'HUMAN_CONTROLLED' ? 'STAFF' : 'AI'}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Reservations by expiry" linkTo="/reservations" linkLabel="All reservations →">
          {loading ? (
            <PanelSkeleton />
          ) : upcomingReservations.length === 0 ? (
            <PanelMessage>No active reservations.</PanelMessage>
          ) : (
            <ul className="divide-y divide-slate-100">
              {upcomingReservations.map((r) => {
                const expires = parseServerDate(r.expiry_date);
                const overdue = expires.getTime() < Date.now();
                return (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-slate-800">
                        {productById[r.product_id]?.name || `Product #${r.product_id}`}
                      </p>
                      <p className="text-xs text-slate-500">Customer #{r.customer_id}</p>
                    </div>
                    <span className={`text-xs ${overdue ? 'text-red-600 font-medium' : 'text-slate-500'}`}>
                      {overdue ? 'Expired' : 'Expires'}{' '}
                      {expires.toLocaleDateString('en-PH', { month: 'short', day: 'numeric' })}
                    </span>
                    <StatusBadge status={r.status} />
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        <Panel title="Open repairs" linkTo="/repairs" linkLabel="All repairs →">
          {loading ? (
            <PanelSkeleton />
          ) : openRepairs.length === 0 ? (
            <PanelMessage>No open repair jobs.</PanelMessage>
          ) : (
            <ul className="divide-y divide-slate-100">
              {openRepairs.slice(0, 5).map((r) => (
                <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">{r.device_model}</p>
                    <p className="truncate text-xs text-slate-500">{r.issue_description}</p>
                  </div>
                  <span className="text-xs text-slate-500 tabular-nums">
                    {peso.format(Number(r.estimated_cost || 0))}
                  </span>
                  <StatusBadge status={r.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Low stock" linkTo="/inventory" linkLabel="Inventory →">
          {loading ? (
            <PanelSkeleton />
          ) : lowStock.length === 0 ? (
            <PanelMessage>
              {products.length === 0
                ? 'No products yet — add your first one on the Inventory page.'
                : 'Everything is well stocked.'}
            </PanelMessage>
          ) : (
            <ul className="divide-y divide-slate-100">
              {lowStock.slice(0, 5).map((p) => (
                <li key={p.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">{p.name}</p>
                    <p className="text-xs text-slate-500">{peso.format(Number(p.selling_price || 0))}</p>
                  </div>
                  <StatusBadge count={p.count} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
