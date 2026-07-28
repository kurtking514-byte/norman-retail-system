/**
 * Live Chat Dashboard
 *
 * Wired to real backend endpoints:
 *   GET /api/v1/conversations         — thread list (left panel)
 *   GET /api/v1/conversations/{id}    — full message history (right panel)
 *   POST /api/v1/conversations/{id}/reply — send staff reply
 *   GET  /api/v1/notifications?status=Pending — handoff queue
 *   PATCH /api/v1/notifications/{id}   — mark notification resolved
 *
 * Uses the shared api.js Axios instance for all requests.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import StatusBadge from '../components/common/StatusBadge';

// =========================================================================
// Helpers
// =========================================================================

function formatTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return formatTime(dateStr);
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday ${formatTime(dateStr)}`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + formatTime(dateStr);
}

// =========================================================================
// Conversation Thread Item — left panel
// =========================================================================

function ConversationThread({ thread, isSelected, onSelect }) {
  return (
    <button
      onClick={() => onSelect(thread.messenger_user_id)}
      className={`w-full text-left px-4 py-3 hover:bg-slate-50 transition-colors ${
        isSelected ? 'bg-blue-50 border-l-2 border-blue-600' : ''
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-slate-800 truncate">
          {thread.customer_name}
        </span>
        <span className="text-xs text-slate-400 flex-shrink-0 ml-2">
          {formatDate(thread.last_message_timestamp)}
        </span>
      </div>
      <p className="text-xs text-slate-500 truncate mb-1">
        {thread.last_message_text}
      </p>
      <div className="flex items-center gap-2">
        {thread.unread_handoff && (
          <span className="text-xs text-amber-600 font-medium flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-500 inline-block" />
            Needs Attention
          </span>
        )}
      </div>
    </button>
  );
}

// =========================================================================
// Message Bubble — right panel
// =========================================================================

function MessageBubble({ message }) {
  let alignClass = 'justify-start';
  let bubbleClass = 'bg-slate-100 text-slate-700';
  let label = message.speaker;

  if (message.speaker === 'User') {
    alignClass = 'justify-end';
    bubbleClass = 'bg-blue-600 text-white';
  } else if (message.speaker === 'Staff') {
    bubbleClass = 'bg-slate-200 text-slate-700';
  }

  return (
    <div className={`flex ${alignClass}`}>
      <div className={`max-w-[70%] rounded-xl px-4 py-2.5 text-sm ${bubbleClass}`}>
        <div className="text-xs font-medium mb-0.5 opacity-70">{label}</div>
        <p>{message.message_text}</p>
        <div className={`text-xs mt-1 ${message.speaker === 'User' ? 'text-blue-200' : 'text-slate-400'}`}>
          {formatTime(message.timestamp)}
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// Customer Profile Panel — third column
// =========================================================================

function CustomerProfile({ customerId, customerName }) {
  const [reservations, setReservations] = useState([]);
  const [repairs, setRepairs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!customerId) {
      setReservations([]);
      setRepairs([]);
      return;
    }

    const fetchCustomerData = async () => {
      setLoading(true);
      try {
        const [resRes, repRes] = await Promise.all([
          api.get('/reservations', { params: { customer_id: customerId, limit: 10 } }),
          api.get('/repairs', { params: { customer_id: customerId, limit: 10 } }),
        ]);
        setReservations(resRes.data || []);
        setRepairs(repRes.data || []);
      } catch {
        setReservations([]);
        setRepairs([]);
      } finally {
        setLoading(false);
      }
    };

    fetchCustomerData();
  }, [customerId]);

  const activeReservations = reservations.filter(
    (r) => r.status !== 'Cancelled' && r.status !== 'Claimed'
  );
  const activeRepairs = repairs.filter(
    (r) => r.status !== 'Released' && r.status !== 'Cancelled'
  );

  return (
    <div className="w-72 border-l border-slate-200 flex flex-col bg-slate-50">
      <div className="px-4 py-3 border-b border-slate-200">
        <h3 className="text-sm font-semibold text-slate-700">Customer Profile</h3>
      </div>

      {!customerId ? (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm p-4 text-center">
          Select a conversation to view customer details.
        </div>
      ) : loading ? (
        <div className="flex-1 p-4 space-y-3">
          <div className="h-4 bg-slate-200 rounded animate-pulse w-3/4" />
          <div className="h-4 bg-slate-200 rounded animate-pulse w-1/2" />
          <div className="h-10 bg-slate-200 rounded animate-pulse w-full" />
          <div className="h-10 bg-slate-200 rounded animate-pulse w-full" />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-5 text-sm">
          {/* Customer name & ID */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Customer
            </h4>
            <p className="text-slate-800 font-medium">{customerName || 'Unknown'}</p>
            <p className="text-slate-500 text-xs">ID: {customerId}</p>
          </div>

          {/* Active Reservations */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Reservations
              {activeReservations.length > 0 && (
                <span className="ml-1.5 text-blue-600 font-normal">
                  ({activeReservations.length})
                </span>
              )}
            </h4>
            {activeReservations.length === 0 ? (
              <p className="text-slate-400 italic text-xs">No active reservations</p>
            ) : (
              <ul className="space-y-1.5">
                {activeReservations.map((r) => (
                  <li key={r.id} className="bg-white rounded border border-slate-200 px-2.5 py-2">
                    <p className="text-xs font-medium text-slate-700">Reservation #{r.id}</p>
                    <p className="text-xs text-slate-500">Status: {r.status}</p>
                    {r.notes && (
                      <p className="text-xs text-slate-400 truncate mt-0.5">{r.notes}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Active Repair Tickets */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Repair Tickets
              {activeRepairs.length > 0 && (
                <span className="ml-1.5 text-amber-600 font-normal">
                  ({activeRepairs.length})
                </span>
              )}
            </h4>
            {activeRepairs.length === 0 ? (
              <p className="text-slate-400 italic text-xs">No active repairs</p>
            ) : (
              <ul className="space-y-1.5">
                {activeRepairs.map((r) => (
                  <li key={r.id} className="bg-white rounded border border-slate-200 px-2.5 py-2">
                    <p className="text-xs font-medium text-slate-700">{r.device_model}</p>
                    <p className="text-xs text-slate-500">Status: {r.status}</p>
                    {r.estimated_cost && Number(r.estimated_cost) > 0 && (
                      <p className="text-xs text-slate-500">
                        Est. Cost: ₱{Number(r.estimated_cost).toLocaleString()}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// =========================================================================
// Main Component
// =========================================================================

export default function LiveChat() {
  const [threads, setThreads] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [needsAttentionOnly, setNeedsAttentionOnly] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [notificationId, setNotificationId] = useState(null);
  const [threadState, setThreadState] = useState(null);
  const [threadStatePinned, setThreadStatePinned] = useState(false);
  const [togglingAi, setTogglingAi] = useState(false);
  const [togglingPin, setTogglingPin] = useState(false);
  const [sseConnected, setSseConnected] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const messagesEndRef = useRef(null);
  const sseRef = useRef(null);
  const tokenRef = useRef(null);

  // -----------------------------------------------------------------------
  // Get auth token from localStorage for SSE connection
  // -----------------------------------------------------------------------
  useEffect(() => {
    try {
      const token = localStorage.getItem('norman_admin_token');
      tokenRef.current = token || null;
    } catch {
      tokenRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // SSE connection for live real-time updates
  // -----------------------------------------------------------------------
  useEffect(() => {
    const token = tokenRef.current;
    if (!token) return;

    let eventSource = null;

    function connectSSE() {
      if (eventSource) {
        eventSource.close();
      }

      // EventSource doesn't support custom headers, so pass token as query param.
      // FastAPI's OAuth2 password bearer also reads from query param.
      const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      eventSource = new EventSource(
        `${baseUrl}/api/v1/conversations/stream?token=${encodeURIComponent(token)}`
      );
      sseRef.current = eventSource;

      eventSource.addEventListener('connected', () => {
        setSseConnected(true);
      });

      eventSource.addEventListener('message', (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'new_message') {
            // Update thread list: bump the conversation to top, update
            // last_message_text and last_message_timestamp
            setThreads((prev) => {
              const existing = prev.find(
                (t) => t.messenger_user_id === data.messenger_user_id
              );
              if (!existing) {
                // New unseen thread — trigger a full refresh to load
                // customer name, etc.
                return prev;
              }
              return prev
                .map((t) =>
                  t.messenger_user_id === data.messenger_user_id
                    ? {
                        ...t,
                        last_message_text: data.message,
                        last_message_timestamp: data.timestamp,
                      }
                    : t,
                )
                .sort(
                  (a, b) =>
                    new Date(b.last_message_timestamp) -
                    new Date(a.last_message_timestamp)
                );
            });

            // If the message is for the currently selected thread, append it
            if (data.messenger_user_id === selectedUserId) {
              setMessages((prev) => {
                const isDuplicate = prev.some(
                  (m) =>
                    m.speaker === data.speaker &&
                    m.timestamp === data.timestamp &&
                    m.message_text === data.message,
                );
                if (isDuplicate) return prev;
                return [
                  ...prev,
                  {
                    id: Date.now(),
                    speaker: data.speaker,
                    message_text: data.message,
                    timestamp: data.timestamp,
                  },
                ];
              });
            }
          } else if (data.type === 'thread_state_changed') {
            setThreads((prev) =>
              prev.map((t) =>
                t.messenger_user_id === data.messenger_user_id
                  ? {
                      ...t,
                      thread_state: data.new_state,
                      thread_state_pinned: data.thread_state_pinned ?? false,
                    }
                  : t,
              ),
            );
            if (data.messenger_user_id === selectedUserId) {
              setThreadState(data.new_state);
              setThreadStatePinned(data.thread_state_pinned ?? false);
            }
          }
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
        }
      });

      eventSource.onerror = () => {
        setSseConnected(false);
        console.warn('SSE connection lost, will auto-reconnect...');
      };

      eventSource.onopen = () => {
        setSseConnected(true);
      };
    }

    connectSSE();

    return () => {
      if (eventSource) {
        eventSource.close();
        sseRef.current = null;
      }
    };
  }, [selectedUserId]);

  // -----------------------------------------------------------------------
  // Fetch conversation thread list
  // -----------------------------------------------------------------------
  const fetchThreads = useCallback(async () => {
    try {
      const res = await api.get('/conversations');
      setThreads(res.data);
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to load conversations.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    }
  }, []);

  useEffect(() => {
    fetchThreads();
  }, [fetchThreads]);

  // -----------------------------------------------------------------------
  // Manual refresh button handler
  // -----------------------------------------------------------------------
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchThreads();
    } finally {
      setRefreshing(false);
    }
  }, [fetchThreads]);

  // -----------------------------------------------------------------------
  // When a thread is selected, fetch its full message history
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!selectedUserId) {
      setMessages([]);
      setNotificationId(null);
      return;
    }

    const fetchMessages = async () => {
      setMessagesLoading(true);
      try {
        const res = await api.get(`/conversations/${selectedUserId}`);
        setMessages(res.data);
      } catch (err) {
        const data = err.response?.data;
        let msg = 'Failed to load messages.';
        if (data?.detail?.error?.message) msg = data.detail.error.message;
        else if (data?.error?.message) msg = data.error.message;
        setError(msg);
      } finally {
        setMessagesLoading(false);
      }
    };

    fetchMessages();
  }, [selectedUserId]);

  // -----------------------------------------------------------------------
  // Determine the notification_id for the "Mark Resolved" button
  // Look for a Pending notification whose payload.messenger_user_id matches
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!selectedUserId) {
      setNotificationId(null);
      return;
    }

    const fetchNotificationId = async () => {
      try {
        const res = await api.get('/notifications', { params: { status: 'Pending' } });
        const notifications = res.data;
        const match = notifications.find(
          (n) => n.payload && n.payload.messenger_user_id === selectedUserId,
        );
        setNotificationId(match ? match.id : null);
      } catch {
        setNotificationId(null);
      }
    };

    fetchNotificationId();
  }, [selectedUserId, threads]);

  // -----------------------------------------------------------------------
  // Find selected thread's data for the header, thread_state tracking, etc.
  // -----------------------------------------------------------------------
  const selectedThread = threads.find((t) => t.messenger_user_id === selectedUserId);

  // -----------------------------------------------------------------------
  // Track thread_state and thread_state_pinned from the selected thread data
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (selectedThread?.thread_state) {
      setThreadState(selectedThread.thread_state);
      setThreadStatePinned(selectedThread.thread_state_pinned ?? false);
    } else {
      setThreadState(null);
      setThreadStatePinned(false);
    }
  }, [selectedThread?.thread_state, selectedThread?.thread_state_pinned, selectedThread?.messenger_user_id]);

  // -----------------------------------------------------------------------
  // Toggle AI control state
  // -----------------------------------------------------------------------
  const handleToggleAi = async () => {
    if (!selectedUserId) return;

    const newState = threadState === 'HUMAN_CONTROLLED' ? 'AI_CONTROLLED' : 'HUMAN_CONTROLLED';

    setTogglingAi(true);
    setError('');
    try {
      const res = await api.patch(`/conversations/${selectedUserId}/thread-state`, {
        thread_state: newState,
      });
      setThreadState(newState);
      setThreadStatePinned(res.data.thread_state_pinned ?? false);
      // Update the thread in the local list so the toggle reflects immediately
      setThreads((prev) =>
        prev.map((t) =>
          t.messenger_user_id === selectedUserId
            ? { ...t, thread_state: newState, thread_state_pinned: res.data.thread_state_pinned ?? false }
            : t,
        ),
      );
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to toggle AI state.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    } finally {
      setTogglingAi(false);
    }
  };

  // -----------------------------------------------------------------------
  // Auto-scroll to bottom when messages change
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // -----------------------------------------------------------------------
  // Filter: Needs Attention only
  // -----------------------------------------------------------------------
  const filteredThreads = needsAttentionOnly
    ? threads.filter((t) => t.unread_handoff)
    : threads;

  // -----------------------------------------------------------------------
  // Send staff reply
  // -----------------------------------------------------------------------
  const handleSendReply = async () => {
    const text = replyText.trim();
    if (!text || !selectedUserId) return;

    setSending(true);
    setError('');
    try {
      const res = await api.post(`/conversations/${selectedUserId}/reply`, {
        message_text: text,
      });
      // Append the sent message to the local messages array
      const newMsg = res.data;
      setMessages((prev) => [...prev, newMsg]);
      setReplyText('');
      // Refresh the thread list to update last_message_text/timestamp
      fetchThreads();
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to send reply.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    } finally {
      setSending(false);
    }
  };

  // Handle Enter key to send
  const handleReplyKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendReply();
    }
  };

  // -----------------------------------------------------------------------
  // Toggle thread_state_pinned (keep paused / don't auto-resume)
  // -----------------------------------------------------------------------
  const handleTogglePin = async () => {
    if (!selectedUserId) return;

    const newPinned = !threadStatePinned;

    setTogglingPin(true);
    setError('');
    try {
      const res = await api.patch(`/conversations/${selectedUserId}/thread-state/pin`, {
        thread_state_pinned: newPinned,
      });
      setThreadStatePinned(newPinned);
      // Update the thread in the local list
      setThreads((prev) =>
        prev.map((t) =>
          t.messenger_user_id === selectedUserId
            ? { ...t, thread_state_pinned: newPinned }
            : t,
        ),
      );
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to toggle pin.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    } finally {
      setTogglingPin(false);
    }
  };

  // -----------------------------------------------------------------------
  // Mark notification as Resolved
  // -----------------------------------------------------------------------
  const handleMarkResolved = async () => {
    if (!notificationId) return;

    setError('');
    try {
      await api.patch(`/notifications/${notificationId}`, {
        status: 'Resolved',
      });
      setNotificationId(null);
      // Refresh thread list so unread_handoff flags update
      fetchThreads();
    } catch (err) {
      const data = err.response?.data;
      let msg = 'Failed to mark as resolved.';
      if (data?.detail?.error?.message) msg = data.detail.error.message;
      else if (data?.error?.message) msg = data.error.message;
      setError(msg);
    }
  };

  // ======================================================================
  // Render
  // ======================================================================

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Live Chat</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Monitor conversations and handle handoffs
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Connection status indicator */}
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-medium ${
              sseConnected ? 'text-emerald-600' : 'text-slate-400'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                sseConnected
                  ? 'bg-emerald-500 animate-pulse'
                  : 'bg-slate-300'
              }`}
            />
            {sseConnected ? 'Live' : 'Reconnecting...'}
          </span>
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={needsAttentionOnly}
            onChange={() => setNeedsAttentionOnly(!needsAttentionOnly)}
            className="text-blue-600 rounded"
          />
          Needs Attention
        </label>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 ml-2">&times;</button>
        </div>
      )}

      {/* Chat layout — three columns */}
      <div className="flex flex-1 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm min-h-[500px]">
        {/* ============================================================ */}
        {/* Conversation list — left column                             */}
        {/* ============================================================ */}
        <div className="w-80 border-r border-slate-200 flex flex-col">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700">
              Conversations
              <span className="ml-2 text-xs font-normal text-slate-400">
                ({filteredThreads.length})
              </span>
            </h3>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="text-xs text-slate-500 hover:text-blue-600 disabled:text-slate-300 transition-colors px-2 py-0.5 rounded flex items-center gap-1"
              title="Refresh conversation list"
            >
              <svg
                className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {refreshing ? '' : 'Refresh'}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {filteredThreads.length === 0 ? (
              <div className="p-6 text-center text-sm text-slate-400">
                {needsAttentionOnly
                  ? 'No conversations need attention.'
                  : 'No conversations yet.'}
              </div>
            ) : (
              filteredThreads.map((thread) => (
                <ConversationThread
                  key={thread.messenger_user_id}
                  thread={thread}
                  isSelected={selectedUserId === thread.messenger_user_id}
                  onSelect={setSelectedUserId}
                />
              ))
            )}
          </div>
        </div>

        {/* ============================================================ */}
        {/* Message thread — center column                              */}
        {/* ============================================================ */}
        <div className="flex-1 flex flex-col">
          {selectedUserId && selectedThread ? (
            <>
              {/* Thread header */}
              <div className="px-6 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      {selectedThread.customer_name}
                    </h3>
                    {selectedThread.unread_handoff && (
                      <StatusBadge status="Pending" />
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {/* AI Toggle button */}
                  <button
                    onClick={handleToggleAi}
                    disabled={togglingAi}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                      threadState === 'HUMAN_CONTROLLED'
                        ? 'bg-amber-100 text-amber-700 hover:bg-amber-200 border border-amber-300'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-300'
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                    title={
                      threadState === 'HUMAN_CONTROLLED'
                        ? 'AI is paused — click to resume'
                        : 'AI is active — click to pause'
                    }
                  >
                    {togglingAi
                      ? '...'
                      : threadState === 'HUMAN_CONTROLLED'
                        ? 'AI Paused'
                        : 'AI Active'}
                  </button>

                  {/* Keep Paused checkbox — only meaningful when HUMAN_CONTROLLED */}
                  {threadState === 'HUMAN_CONTROLLED' && (
                    <label
                      className={`flex items-center gap-1.5 text-xs cursor-pointer select-none px-2 py-1 rounded border ${
                        threadStatePinned
                          ? 'bg-purple-50 border-purple-300 text-purple-700'
                          : 'bg-slate-50 border-slate-300 text-slate-500'
                      }`}
                      title={
                        threadStatePinned
                          ? 'Auto-resume is disabled — click to allow'
                          : 'Click to keep paused and prevent auto-resume'
                      }
                    >
                      <input
                        type="checkbox"
                        checked={threadStatePinned}
                        onChange={handleTogglePin}
                        disabled={togglingPin}
                        className="w-3 h-3 text-purple-600 rounded"
                      />
                      {togglingPin ? '...' : 'Keep Paused'}
                    </label>
                  )}

                  {/* Mark Resolved button — only visible when there's a Pending notification */}
                  {notificationId && (
                    <button
                      onClick={handleMarkResolved}
                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors"
                    >
                      Mark Resolved
                    </button>
                  )}
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {messagesLoading ? (
                  <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="flex justify-start">
                        <div className="w-2/3 h-14 bg-slate-100 rounded-xl animate-pulse" />
                      </div>
                    ))}
                  </div>
                ) : messages.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-slate-400 text-sm">
                    No messages in this thread yet.
                  </div>
                ) : (
                  messages.map((msg) => (
                    <MessageBubble key={msg.id || `${msg.speaker}-${msg.timestamp}`} message={msg} />
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Reply input */}
              <div className="px-6 py-3 border-t border-slate-200 bg-slate-50">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onKeyDown={handleReplyKeyDown}
                    placeholder="Type your reply..."
                    disabled={sending}
                    className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-slate-100 disabled:cursor-not-allowed"
                  />
                  <button
                    onClick={handleSendReply}
                    disabled={sending || !replyText.trim()}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                      sending || !replyText.trim()
                        ? 'bg-slate-300 text-white cursor-not-allowed'
                        : 'bg-blue-600 hover:bg-blue-700 text-white'
                    }`}
                  >
                    {sending ? 'Sending...' : 'Send'}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              <div className="text-center">
                <p className="text-lg font-medium mb-1">Select a conversation</p>
                <p className="text-sm">Choose a thread from the left panel to view messages.</p>
              </div>
            </div>
          )}
        </div>

        {/* ============================================================ */}
        {/* Customer profile — right column                             */}
        {/* ============================================================ */}
        <CustomerProfile
          customerId={selectedThread?.customer_id}
          customerName={selectedThread?.customer_name}
        />
      </div>
    </div>
  );
}
