import { useState, useRef } from 'react';
import api from '../../services/api';

/**
 * Bulk import of phones from an Excel/CSV file.
 *
 * Flow: download template → choose file → preview (nothing saved) →
 * import. The backend only applies the file when every row is valid.
 */

const ACTION_STYLES = {
  create: { label: 'New', className: 'bg-terrace-100 text-terrace-700' },
  update: { label: 'Update', className: 'bg-brand-100 text-brand-700' },
  unchanged: { label: 'No change', className: 'bg-stone-100 text-stone-500' },
  error: { label: 'Error', className: 'bg-red-100 text-red-700' },
};

function errorMessage(err, fallback) {
  const data = err.response?.data;
  return data?.error?.message || data?.detail?.error?.message || fallback;
}

function stockText(row) {
  if (row.stock_target === null || row.stock_target === undefined) return 'Keep';
  if (row.stock_current === null || row.stock_current === undefined) return `${row.stock_target}`;
  if (row.stock_current === row.stock_target) return `${row.stock_target}`;
  return `${row.stock_current} → ${row.stock_target}`;
}

export default function ImportProductsModal({ open, onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [onlyProblems, setOnlyProblems] = useState(false);
  const inputRef = useRef(null);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError('');
    setOnlyProblems(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  const close = () => {
    reset();
    onClose();
  };

  const downloadTemplate = async () => {
    setBusy('template');
    setError('');
    try {
      const res = await api.get('/products/import/template', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'phone-import-template.xlsx';
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError('Could not download the template.');
    } finally {
      setBusy('');
    }
  };

  const upload = async (dryRun) => {
    if (!file) return;
    setBusy(dryRun ? 'preview' : 'import');
    setError('');
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await api.post('/products/import', form, { params: { dry_run: dryRun } });
      if (dryRun) {
        setPreview(res.data);
        setOnlyProblems(res.data.summary.error > 0);
      } else {
        setResult(res.data);
        onImported();
      }
    } catch (err) {
      setError(errorMessage(err, 'Upload failed. Please try again.'));
    } finally {
      setBusy('');
    }
  };

  const chooseFile = (e) => {
    const chosen = e.target.files?.[0] || null;
    setFile(chosen);
    setPreview(null);
    setResult(null);
    setError('');
  };

  if (!open) return null;

  const summary = (result || preview)?.summary;
  const rows = preview?.rows || [];
  const visibleRows = onlyProblems
    ? rows.filter((r) => r.errors.length || r.warnings.length)
    : rows;
  const changes = summary ? summary.create + summary.update : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-stone-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-stone-800">Import phones from a spreadsheet</h2>
          <button onClick={close} className="text-stone-400 hover:text-stone-600 text-xl leading-none">&times;</button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto min-h-0">
          {/* Step 1 & 2 */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-stone-200 p-4">
              <p className="text-sm font-semibold text-stone-700">1. Fill in the template</p>
              <p className="mt-1 text-xs text-stone-500">
                One row per phone model. Re-uploading updates phones with the same model number.
              </p>
              <button
                onClick={downloadTemplate}
                disabled={busy === 'template'}
                className="mt-3 px-3 py-2 text-sm font-medium text-brand-700 bg-brand-50 hover:bg-brand-100 rounded-lg disabled:opacity-50"
              >
                {busy === 'template' ? 'Downloading…' : 'Download Excel template'}
              </button>
            </div>
            <div className="rounded-lg border border-stone-200 p-4">
              <p className="text-sm font-semibold text-stone-700">2. Upload your file</p>
              <p className="mt-1 text-xs text-stone-500">Excel (.xlsx) or CSV, up to 5,000 phones.</p>
              <input
                ref={inputRef}
                type="file"
                accept=".xlsx,.csv"
                onChange={chooseFile}
                className="mt-3 block w-full text-sm text-stone-600 file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border-0 file:bg-stone-100 file:text-stone-700 file:text-sm file:font-medium hover:file:bg-stone-200"
              />
            </div>
          </div>

          {error && (
            <div className="px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">{error}</div>
          )}

          {/* Result */}
          {result && (
            <div className="px-4 py-3 bg-terrace-50 border border-terrace-200 text-terrace-800 text-sm rounded-lg">
              <p className="font-semibold">Import complete.</p>
              <p>
                {summary.create} new, {summary.update} updated, {summary.unchanged} unchanged.
                Stock: +{summary.stock_added} / −{summary.stock_removed} units.
              </p>
            </div>
          )}

          {/* Preview */}
          {preview && !result && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-semibold text-stone-700">Preview — nothing saved yet:</span>
                <span className="px-2 py-0.5 rounded bg-terrace-100 text-terrace-700">{summary.create} new</span>
                <span className="px-2 py-0.5 rounded bg-brand-100 text-brand-700">{summary.update} updated</span>
                <span className="px-2 py-0.5 rounded bg-stone-100 text-stone-600">{summary.unchanged} unchanged</span>
                {summary.error > 0 && (
                  <span className="px-2 py-0.5 rounded bg-red-100 text-red-700">{summary.error} with errors</span>
                )}
                <label className="ml-auto flex items-center gap-1.5 text-xs text-stone-500 cursor-pointer">
                  <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
                  Only rows with errors or notes
                </label>
              </div>

              {summary.error > 0 && (
                <p className="text-sm text-red-700">
                  Fix the rows marked Error in your file, then choose it again. Nothing is imported until every row is valid.
                </p>
              )}

              <div className="border border-stone-200 rounded-lg overflow-hidden">
                <div className="max-h-80 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-stone-50 text-stone-500 text-xs uppercase sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium">Row</th>
                        <th className="px-3 py-2 text-left font-medium">Phone</th>
                        <th className="px-3 py-2 text-left font-medium">Result</th>
                        <th className="px-3 py-2 text-left font-medium">Stock</th>
                        <th className="px-3 py-2 text-left font-medium">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-100">
                      {visibleRows.map((r) => (
                        <tr key={r.row} className="align-top">
                          <td className="px-3 py-2 text-stone-400 tabular-nums">{r.row}</td>
                          <td className="px-3 py-2 min-w-0">
                            <p className="font-medium text-stone-800 break-words">{r.name || '—'}</p>
                            <p className="text-xs text-stone-500 break-all">{r.model_number}</p>
                          </td>
                          <td className="px-3 py-2">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_STYLES[r.action].className}`}>
                              {ACTION_STYLES[r.action].label}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-stone-600 tabular-nums whitespace-nowrap">{stockText(r)}</td>
                          <td className="px-3 py-2 text-xs">
                            {r.errors.map((e) => (
                              <p key={e} className="text-red-600">{e}</p>
                            ))}
                            {r.warnings.map((w) => (
                              <p key={w} className="text-amber-600">{w}</p>
                            ))}
                          </td>
                        </tr>
                      ))}
                      {visibleRows.length === 0 && (
                        <tr>
                          <td colSpan={5} className="px-3 py-6 text-center text-stone-400">No rows to show.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-stone-200 flex justify-end gap-3">
          {result ? (
            <button onClick={close} className="px-4 py-2 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg">
              Done
            </button>
          ) : (
            <>
              <button onClick={close} className="px-4 py-2 text-sm font-medium text-stone-700 bg-stone-100 hover:bg-stone-200 rounded-lg">
                Cancel
              </button>
              {!preview ? (
                <button
                  onClick={() => upload(true)}
                  disabled={!file || busy === 'preview'}
                  className="px-4 py-2 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg disabled:bg-brand-300 disabled:cursor-not-allowed"
                >
                  {busy === 'preview' ? 'Checking…' : 'Preview import'}
                </button>
              ) : (
                <button
                  onClick={() => upload(false)}
                  disabled={summary.error > 0 || changes === 0 || busy === 'import'}
                  className="px-4 py-2 text-sm font-semibold text-white bg-terrace-600 hover:bg-terrace-700 rounded-lg disabled:bg-stone-300 disabled:cursor-not-allowed"
                >
                  {busy === 'import'
                    ? 'Importing…'
                    : changes === 0
                      ? 'Nothing to import'
                      : `Import ${changes} phone${changes !== 1 ? 's' : ''}`}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
