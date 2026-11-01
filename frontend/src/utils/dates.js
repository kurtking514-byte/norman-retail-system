/**
 * The backend stores and returns timestamps as UTC without a timezone suffix
 * (e.g. "2026-11-01T02:06:00"). JavaScript would read those as local time, so
 * add the "Z" before parsing so they display in the viewer's own timezone.
 */
export function parseServerDate(value) {
  if (!value) return new Date(NaN);
  if (value instanceof Date) return value;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  return new Date(hasZone || isDateOnly ? value : `${value}Z`);
}
