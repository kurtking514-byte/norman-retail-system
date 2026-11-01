import { useState, useEffect } from 'react';
import api from '../../services/api';

/**
 * Global AI chatbot on/off switch shown in the dashboard top bar.
 * When off, customer messages are still saved and shown in Live Chat,
 * but the AI does not reply to anyone.
 */
export default function AiSwitch({ onDark = false }) {
  const [enabled, setEnabled] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    api
      .get('/settings/ai-replies')
      .then((res) => {
        if (!cancelled) setEnabled(res.data.enabled);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load AI status');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await api.put('/settings/ai-replies', { enabled: !enabled });
      setEnabled(res.data.enabled);
    } catch {
      setError('Could not update AI status');
    } finally {
      setSaving(false);
    }
  };

  if (enabled === null) {
    return error ? <span className="text-xs text-red-600">{error}</span> : null;
  }

  return (
    <div className="flex items-center gap-3">
      {error && <span className="text-xs text-red-600">{error}</span>}
      <span className={`text-sm ${onDark ? 'text-stone-300' : 'text-stone-600'}`}>
        AI chatbot:{' '}
        <span className={`font-semibold ${enabled ? (onDark ? 'text-white' : 'text-terrace-600') : (onDark ? 'text-brand-300' : 'text-red-600')}`}>
          {enabled ? 'On' : 'Off'}
        </span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label="Toggle AI chatbot replies"
        title={
          enabled
            ? 'AI replies to customers automatically. Click to turn off.'
            : 'AI is off — customers will not get automatic replies. Click to turn on.'
        }
        onClick={toggle}
        disabled={saving}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
          enabled ? 'bg-terrace-500' : onDark ? 'bg-stone-500' : 'bg-stone-300'
        }`}
      >
        <span
          className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
            enabled ? 'translate-x-5' : 'translate-x-0.5'
          }`}
        />
      </button>
    </div>
  );
}
