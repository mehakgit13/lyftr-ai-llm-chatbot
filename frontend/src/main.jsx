
import React, { Component, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Bot,
  Send,
  Sparkles,
  User,
  RotateCcw,
  Activity,
  Zap,
  Cpu,
  Coins
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './style.css';

const API_BASE = (
  import.meta.env.VITE_API_URL || 'http://localhost:8000'
).replace(/\/$/, '');

function makeSessionId() {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return `s-${crypto.randomUUID()}`;
  }

  return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/* Prevents a rendering error from leaving the application blank. */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error('Chat interface rendering error:', error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="fatal-error" role="alert">
          <h1>Lyftr AI could not display this screen</h1>
          <p>
            The interface encountered an unexpected error.
            Refresh the page to try again.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
          >
            Refresh application
          </button>
        </main>
      );
    }

    return this.props.children;
  }
}

function App() {
  const [sessionId, setSessionId] = useState(makeSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showPrompt, setShowPrompt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [health, setHealth] = useState('checking');

  const endRef = useRef(null);

  /* Backend health check with explicit cleanup. */
  useEffect(() => {
    let cancelled = false;

    async function checkHealth() {
      try {
        const response = await fetch(`${API_BASE}/health`);

        if (!response.ok) {
          throw new Error('Backend health check failed');
        }

        if (!cancelled) {
          setHealth('online');
        }
      } catch {
        if (!cancelled) {
          setHealth('offline');
        }
      }
    }

    checkHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  /* Scroll to the latest message. */
  useEffect(() => {
    const element = endRef.current;

    if (
      element &&
      typeof element.scrollIntoView === 'function'
    ) {
      element.scrollIntoView({
        behavior: 'smooth',
        block: 'end'
      });
    }
  }, [messages, busy, error]);

  /* Send a message to FastAPI. */
  async function sendMessage(event) {
    if (event) {
      event.preventDefault();
    }

    const text = input.trim();

    if (!text || busy) {
      return;
    }

    setError('');
    setInput('');

    setMessages((previous) => [
      ...previous,
      {
        role: 'user',
        content: text
      }
    ]);

    setBusy(true);

    try {
      const body = {
        session_id: sessionId,
        message: text
      };

      if (systemPrompt.trim()) {
        body.system_prompt = systemPrompt.trim();
      }

      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      let data;

      try {
        data = await response.json();
      } catch {
        data = {
          detail: 'The server returned an unreadable response.'
        };
      }

      if (!response.ok) {
        const errorMessage =
          typeof data?.detail === 'string'
            ? data.detail
            : `Request failed with HTTP ${response.status}.`;

        throw new Error(errorMessage);
      }

      if (
        typeof data?.reply !== 'string' ||
        !data.reply.trim()
      ) {
        throw new Error(
          'The server returned an empty assistant response.'
        );
      }

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata || null
        }
      ]);
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'Unable to reach the server. Please try again.';

      setError(message);
    } finally {
      setBusy(false);
    }
  }

  /* Start a new conversation. */
  function newChat() {
    setSessionId(makeSessionId());
    setMessages([]);
    setError('');
    setInput('');
  }

  return (
    <div className="app-shell">

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Sparkles size={20} />
          </div>

          <div>
            <b>lyftr<span>.ai</span></b>
            <small>FULL-STACK ASSIGNMENT</small>
          </div>
        </div>

        <button
          className="new-chat"
          type="button"
          onClick={newChat}
        >
          <RotateCcw size={16} />
          New conversation
        </button>

        <div className="side-note">
          <span className={`dot ${health}`} />
          <div>
            <b>Backend {health}</b>
            <small>{API_BASE}</small>
          </div>
        </div>

        <div className="sidebar-bottom">
          <span>POWERED BY</span>
          <b>React · FastAPI · LiteLLM</b>
        </div>
      </aside>

      {/* Main application */}
      <main className="main">

        <header className="topbar">
          <div>
            <span className="eyebrow">AI WORKSPACE</span>
            <h1>Chat assistant</h1>
          </div>

          <button
            className="prompt-toggle"
            type="button"
            onClick={() => setShowPrompt((value) => !value)}
          >
            System prompt {showPrompt ? '−' : '+'}
          </button>
        </header>

        {/* Optional system prompt */}
        {showPrompt && (
          <div className="prompt-panel">
            <label htmlFor="system-prompt-input">
              Session system prompt
            </label>

            <textarea
              id="system-prompt-input"
              data-testid="system-prompt-input"
              value={systemPrompt}
              onChange={(event) =>
                setSystemPrompt(event.target.value)
              }
              placeholder="Optional: define how the assistant should behave..."
              rows="2"
            />
          </div>
        )}

        {/* Chat area */}
        <section className="chat-area" aria-live="polite">

          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-icon">
                <Bot size={30} />
              </div>

              <span className="eyebrow">
                YOUR AI ASSISTANT
              </span>

              <h2>
                What can I help you
                <br />
                work through today?
              </h2>

              <p>
                Ask a question to start a conversation.
                Your chat context is stored securely in SQLite.
              </p>

              <div className="suggestions">
                <button
                  type="button"
                  onClick={() =>
                    setInput('Explain how API key failover works.')
                  }
                >
                  Explain key failover
                </button>

                <button
                  type="button"
                  onClick={() =>
                    setInput(
                      'What is response caching and why is it useful?'
                    )
                  }
                >
                  Explain response caching
                </button>
              </div>
            </div>
          ) : (
            <div className="message-list">

              {messages.map((message, index) => (
                <div
                  className={`message-row ${message.role}`}
                  key={`${sessionId}-${index}`}
                >
                  <div className="avatar">
                    {message.role === 'assistant'
                      ? <Bot size={17} />
                      : <User size={17} />
                    }
                  </div>

                  <div className="message-content">

                    <div className="message-label">
                      {message.role === 'assistant'
                        ? 'LYFTR AI'
                        : 'YOU'
                      }
                    </div>

                    {/* Message bubble */}
                    <div
                      className="bubble"
                      data-testid={
                        message.role === 'assistant'
                          ? 'assistant-message'
                          : undefined
                      }
                    >

                      {/* Render assistant Markdown only once */}
                      {message.role === 'assistant' ? (
                        <div className="markdown-body">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                          >
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        message.content
                      )}

                      {/* Response metadata */}
                      {message.metadata && (
                        <div className="metadata">

                          <div className="meta-chip">
                            <Activity size={13} />
                            <span>Source</span>
                            <b data-testid="meta-source">
                              {message.metadata.resolution_source}
                            </b>
                          </div>

                          <div className="meta-chip">
                            <Cpu size={13} />
                            <span>Model</span>
                            <b data-testid="meta-model">
                              {message.metadata.model}
                            </b>
                          </div>

                          <div className="meta-chip">
                            <Zap size={13} />
                            <span>Latency</span>
                            <b data-testid="meta-latency">
                              {message.metadata.latency_ms} ms
                            </b>
                          </div>

                          <div className="meta-chip">
                            <Coins size={13} />
                            <span>Input</span>
                            <b data-testid="meta-input-tokens">
                              {message.metadata.input_tokens}
                            </b>
                          </div>

                          <div className="meta-chip">
                            <Coins size={13} />
                            <span>Output</span>
                            <b data-testid="meta-output-tokens">
                              {message.metadata.output_tokens}
                            </b>
                          </div>

                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {/* Loading indicator */}
              {busy && (
                <div className="message-row assistant">
                  <div className="avatar">
                    <Bot size={17} />
                  </div>

                  <div
                    className="bubble typing"
                    aria-label="Assistant is responding"
                  >
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              )}

              <div ref={endRef} />
            </div>
          )}
        </section>

        {/* Message composer */}
        <div className="composer-wrap">

          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}

          <form
            className="composer"
            onSubmit={sendMessage}
          >
            <textarea
              data-testid="chat-input"
              value={input}
              onChange={(event) =>
                setInput(event.target.value)
              }
              onKeyDown={(event) => {
                if (
                  event.key === 'Enter' &&
                  !event.shiftKey
                ) {
                  event.preventDefault();
                  sendMessage(event);
                }
              }}
              placeholder="Message Lyftr AI..."
              rows="1"
              disabled={busy}
            />

            <button
              data-testid="send-button"
              type="submit"
              disabled={!input.trim() || busy}
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          </form>

          <div className="composer-foot">
            <span>Enter to send · Shift + Enter for a new line</span>
            <span>AI responses may need verification</span>
          </div>
        </div>
      </main>
    </div>
  );
}

/* Application entry point */
createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);
