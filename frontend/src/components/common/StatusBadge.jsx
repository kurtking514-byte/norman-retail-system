/**
 * StatusBadge – shared colored pill for status values across the app.
 *
 * Usage: <StatusBadge status="Pending" />
 *
 * Color map (consistent across Reservations, Repairs, Inventory):
 *   Pending                     → amber/yellow
 *   Confirmed / Diagnosis       → blue
 *   Claimed / Released / Sold   → green
 *   Cancelled                   → grey
 *   Ready for Pickup            → purple
 *   In Progress                 → blue (same as Diagnosis)
 *   In Stock                    → green
 *   Reserved                    → amber
 *   In Repair                   → blue
 *   Out of Stock                → red
 *   Low (Stock)                 → amber
 */

const statusColors = {
  // Reservation statuses
  Pending: 'bg-amber-100 text-amber-700',
  Confirmed: 'bg-blue-100 text-blue-700',
  Claimed: 'bg-emerald-100 text-emerald-700',
  Cancelled: 'bg-slate-100 text-slate-500',

  // Repair statuses
  Diagnosis: 'bg-blue-100 text-blue-700',
  'In Progress': 'bg-blue-100 text-blue-700',
  'Ready for Pickup': 'bg-purple-100 text-purple-700',
  Released: 'bg-emerald-100 text-emerald-700',

  // Inventory stock states
  'In Stock': 'bg-emerald-100 text-emerald-700',
  Reserved: 'bg-amber-100 text-amber-700',
  'In Repair': 'bg-blue-100 text-blue-700',
  'Out of Stock': 'bg-red-100 text-red-700',
  Sold: 'bg-emerald-100 text-emerald-700',
};

const defaultClass = 'bg-slate-100 text-slate-600';

export default function StatusBadge({ status, count }) {
  // If count is provided, render a stock-count style badge (e.g. "Low (2)", "In Stock (5)")
  if (count !== undefined && count !== null) {
    if (count === 0) {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
          Out of Stock
        </span>
      );
    }
    if (count <= 3) {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
          Low ({count})
        </span>
      );
    }
    return (
      <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
        In Stock ({count})
      </span>
    );
  }

  const colorClass = statusColors[status] || defaultClass;
  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClass}`}>
      {status}
    </span>
  );
}
