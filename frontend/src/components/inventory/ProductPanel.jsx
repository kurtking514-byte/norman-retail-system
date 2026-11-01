import { useState, useEffect } from 'react';
import api from '../../services/api';

/**
 * Slide-over panel to add a product or view/edit an existing one:
 * details, brand/category (pick or add new), specs, active flag and stock.
 */

const SUGGESTED_SPECS = ['RAM', 'Storage', 'Screen', 'Battery', 'Main Camera', 'Chipset', 'Colors'];

const inputClass =
  'w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-stone-50';

function errorMessage(err, fallback) {
  const data = err.response?.data;
  if (data?.error?.message) return data.error.message;
  if (data?.detail?.error?.message) return data.detail.error.message;
  if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg.replace(/^Value error, /, '');
  return fallback;
}

function emptyForm() {
  return {
    name: '',
    model_number: '',
    brand_id: '',
    category_id: '',
    cost_price: '',
    selling_price: '',
    warranty_months: 12,
    description: '',
    is_active: true,
    specs: SUGGESTED_SPECS.slice(0, 2).map((key) => ({ key, value: '' })),
    in_stock: 0,
  };
}

const asText = (value) => (value === null || value === undefined ? '' : String(value));

/** Empty input -> null; otherwise a number (NaN if it isn't one). */
const optionalNumber = (value) => (String(value).trim() === '' ? null : Number(value));

function formFromProduct(product, stock) {
  const specs = Object.entries(product.specifications || {}).map(([key, value]) => ({
    key,
    value: String(value),
  }));
  return {
    name: product.name || '',
    model_number: product.model_number || '',
    brand_id: asText(product.brand_id),
    category_id: asText(product.category_id),
    cost_price: asText(product.cost_price),
    selling_price: asText(product.selling_price),
    warranty_months: product.warranty_months ?? 12,
    description: product.description || '',
    is_active: product.is_active !== false,
    specs: specs.length ? specs : [{ key: '', value: '' }],
    in_stock: stock,
  };
}

/** Select with an inline "+ Add new…" option that creates the name on the server. */
function NamePicker({ label, value, options, onChange, endpoint, onCreated }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const create = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError('');
    try {
      const res = await api.post(endpoint, { name: name.trim() });
      onCreated(res.data);
      onChange(String(res.data.id));
      setAdding(false);
      setName('');
    } catch (err) {
      setError(errorMessage(err, `Could not add ${label.toLowerCase()}.`));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <label className="block text-sm font-medium text-stone-700 mb-1">{label}</label>
      {adding ? (
        <div className="flex gap-2">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                create();
              }
              if (e.key === 'Escape') setAdding(false);
            }}
            placeholder={`New ${label.toLowerCase()} name`}
            className={inputClass}
          />
          <button type="button" onClick={create} disabled={saving}
            className="px-3 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50">
            Add
          </button>
          <button type="button" onClick={() => setAdding(false)}
            className="px-2 text-sm text-stone-500 hover:text-stone-700">
            Cancel
          </button>
        </div>
      ) : (
        <select
          value={value}
          onChange={(e) => (e.target.value === '__new' ? setAdding(true) : onChange(e.target.value))}
          className={inputClass}
        >
          <option value="">None</option>
          {options.map((o) => (
            <option key={o.id} value={String(o.id)}>{o.name}</option>
          ))}
          <option value="__new">+ Add new {label.toLowerCase()}…</option>
        </select>
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export default function ProductPanel({
  open,
  product,
  stock,
  brands,
  categories,
  onClose,
  onSaved,
  onBrandCreated,
  onCategoryCreated,
}) {
  const isNew = !product;
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  // Reset only when the panel opens or switches product — not when the list
  // refreshes after a save, so a save warning stays visible.
  useEffect(() => {
    if (!open) return;
    setForm(product ? formFromProduct(product, stock ?? 0) : emptyForm());
    setError('');
    setNotice('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, product?.id]);

  if (!open) return null;

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  const setSpec = (index, field, value) =>
    setForm((f) => ({
      ...f,
      specs: f.specs.map((s, i) => (i === index ? { ...s, [field]: value } : s)),
    }));
  const usedSpecKeys = new Set(form.specs.map((s) => s.key.trim().toLowerCase()));
  const nextSuggestion = SUGGESTED_SPECS.find((k) => !usedSpecKeys.has(k.toLowerCase())) || '';

  const save = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');

    const cost = optionalNumber(form.cost_price);
    const price = optionalNumber(form.selling_price);
    const stockTarget = parseInt(form.in_stock, 10) || 0;
    if (Number.isNaN(cost) || Number.isNaN(price)) return setError('Enter valid prices.');
    if (cost !== null && price !== null && price <= cost) {
      return setError('Selling price must be higher than cost price.');
    }
    if (stockTarget < 0) return setError('Stock must be 0 or more.');

    const specifications = {};
    for (const { key, value } of form.specs) {
      if (key.trim() && value.trim()) specifications[key.trim()] = value.trim();
    }
    const body = {
      name: form.name.trim() || null,
      model_number: form.model_number.trim() || null,
      brand_id: form.brand_id ? parseInt(form.brand_id, 10) : null,
      category_id: form.category_id ? parseInt(form.category_id, 10) : null,
      cost_price: cost,
      selling_price: price,
      warranty_months: parseInt(form.warranty_months, 10) || 12,
      description: form.description.trim() || null,
      specifications: Object.keys(specifications).length ? specifications : null,
      is_active: form.is_active,
    };

    setSaving(true);
    try {
      const res = isNew
        ? await api.post('/products', body)
        : await api.put(`/products/${product.id}`, body);
      let warning = null;
      if (stockTarget !== (isNew ? 0 : stock ?? 0)) {
        const stockRes = await api.put(`/products/${res.data.id}/stock`, { in_stock: stockTarget });
        warning = stockRes.data.warning;
      }
      onSaved();
      if (warning) {
        setNotice(warning);
      } else {
        onClose();
      }
    } catch (err) {
      setError(errorMessage(err, 'Could not save the product.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <form
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-xl bg-white shadow-2xl flex flex-col"
      >
        <div className="px-6 py-4 border-b border-stone-200 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-stone-800 truncate">
              {isNew ? 'Add product' : product.name}
            </h2>
            {!isNew && product.model_number && <p className="text-xs text-stone-500 truncate">{product.model_number}</p>}
          </div>
          <button type="button" onClick={onClose} className="text-stone-400 hover:text-stone-600 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">{error}</div>
          )}
          {notice && (
            <div className="px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg">
              Saved. {notice}
            </div>
          )}

          {/* Stock */}
          <section className="rounded-lg border border-stone-200 p-4">
            <label className="block text-sm font-semibold text-stone-700">Units in store</label>
            <p className="text-xs text-stone-500 mb-3">How many are on the shelf right now.</p>
            <div className="flex items-center gap-2">
              <button type="button"
                onClick={() => setForm((f) => ({ ...f, in_stock: Math.max(0, (parseInt(f.in_stock, 10) || 0) - 1) }))}
                className="h-9 w-9 rounded-lg border border-stone-300 text-lg text-stone-600 hover:bg-stone-50">
                −
              </button>
              <input type="number" min="0" value={form.in_stock} onChange={set('in_stock')}
                className="h-9 w-24 px-3 border border-stone-300 rounded-lg text-center text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-brand-500" />
              <button type="button"
                onClick={() => setForm((f) => ({ ...f, in_stock: (parseInt(f.in_stock, 10) || 0) + 1 }))}
                className="h-9 w-9 rounded-lg border border-stone-300 text-lg text-stone-600 hover:bg-stone-50">
                +
              </button>
              {!isNew && Number(form.in_stock) !== (stock ?? 0) && (
                <span className="text-xs text-stone-500">was {stock ?? 0}</span>
              )}
            </div>
          </section>

          {/* Details */}
          <section className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-stone-700 mb-1">Name</label>
              <input value={form.name} onChange={set('name')} className={inputClass}
                placeholder="e.g. Galaxy A55 5G 8/256GB" />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-stone-700 mb-1">Model number</label>
              <input value={form.model_number} onChange={set('model_number')} className={inputClass}
                placeholder="e.g. SM-A556E-256 (must be unique if filled in)" />
            </div>
            <NamePicker label="Brand" value={form.brand_id} options={brands} endpoint="/brands"
              onChange={(v) => setForm((f) => ({ ...f, brand_id: v }))} onCreated={onBrandCreated} />
            <NamePicker label="Category" value={form.category_id} options={categories} endpoint="/categories"
              onChange={(v) => setForm((f) => ({ ...f, category_id: v }))} onCreated={onCategoryCreated} />
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-1">Cost price (₱)</label>
              <input type="number" step="0.01" min="0" value={form.cost_price} onChange={set('cost_price')} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-1">Selling price (₱)</label>
              <input type="number" step="0.01" min="0" value={form.selling_price} onChange={set('selling_price')} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-1">Warranty (months)</label>
              <input type="number" min="0" value={form.warranty_months} onChange={set('warranty_months')} className={inputClass} />
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 text-sm text-stone-700 cursor-pointer">
                <input type="checkbox" checked={form.is_active}
                  onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
                Visible (shown to the chatbot)
              </label>
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-stone-700 mb-1">Description</label>
              <textarea rows="2" value={form.description} onChange={set('description')} className={inputClass} />
            </div>
          </section>

          {/* Specs */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-stone-700">Specs</h3>
              <button type="button"
                onClick={() => setForm((f) => ({ ...f, specs: [...f.specs, { key: nextSuggestion, value: '' }] }))}
                className="text-xs font-medium text-brand-600 hover:underline">
                + Add spec
              </button>
            </div>
            <div className="space-y-2">
              {form.specs.map((spec, i) => (
                <div key={i} className="flex gap-2">
                  <input value={spec.key} onChange={(e) => setSpec(i, 'key', e.target.value)}
                    placeholder="Spec (e.g. RAM)" list="spec-suggestions"
                    className={`${inputClass} !w-32 sm:!w-40 flex-shrink-0`} />
                  <input value={spec.value} onChange={(e) => setSpec(i, 'value', e.target.value)}
                    placeholder="Value (e.g. 8GB)" className={`${inputClass} min-w-0`} />
                  <button type="button" aria-label="Remove spec"
                    onClick={() => setForm((f) => ({ ...f, specs: f.specs.filter((_, j) => j !== i) }))}
                    className="px-2 text-stone-400 hover:text-red-600">
                    &times;
                  </button>
                </div>
              ))}
              {form.specs.length === 0 && <p className="text-xs text-stone-400">No specs yet.</p>}
            </div>
            <datalist id="spec-suggestions">
              {SUGGESTED_SPECS.map((k) => <option key={k} value={k} />)}
            </datalist>
          </section>
        </div>

        <div className="px-6 py-4 border-t border-stone-200 flex justify-end gap-3">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-stone-700 bg-stone-100 hover:bg-stone-200 rounded-lg">
            {notice ? 'Close' : 'Cancel'}
          </button>
          <button type="submit" disabled={saving}
            className="px-4 py-2 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg disabled:bg-brand-300">
            {saving ? 'Saving…' : isNew ? 'Add product' : 'Save changes'}
          </button>
        </div>
      </form>
    </div>
  );
}
