"use client";

import { useState, useRef, useEffect } from 'react';

type Message = {
  id: string;
  role: 'user' | 'agent';
  content: string;
};

type Insights = {
  status: string;
  product_area: string;
  confidence: number;
  justification: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'agent',
      content: 'Hello! I am the Support Triage Agent. Please describe your issue.',
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [insights, setInsights] = useState<Insights | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const thoughtLogRef = useRef<HTMLDivElement>(null);
  const isAutoScrollEnabled = useRef(true);

  const [logs, setLogs] = useState<{type: string, message: string}[]>([]);
  
  const scrollToBottomChat = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottomChat();
  }, [messages]);

  const handleThoughtLogScroll = () => {
    if (!thoughtLogRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = thoughtLogRef.current;
    isAutoScrollEnabled.current = scrollHeight - scrollTop - clientHeight < 15;
  };

  useEffect(() => {
    if (isAutoScrollEnabled.current && thoughtLogRef.current) {
      thoughtLogRef.current.scrollTop = thoughtLogRef.current.scrollHeight;
    }
  }, [logs]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: userMessage }]);
    setIsLoading(true);
    setLogs([]); // Clear previous logs
    setInsights(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          issue_text: userMessage,
          subject: "Live Chat Ticket",
          company: "HackerRank User",
          history: messages.map(m => ({ role: m.role, content: m.content })).slice(-10)
        }),
      });

      if (!response.ok) throw new Error('Failed to fetch response');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            
            if (event.type === 'cache') {
              setLogs(prev => [...prev, { type: 'system', message: event.status === 'hit' ? '✓ Cache hit' : '○ Cache miss' }]);
            }
            else if (event.type === 'step') {
              setLogs(prev => [...prev, { type: 'thought', message: `Step ${event.step}: ${event.thought}` }]);
              setLogs(prev => [...prev, { type: 'action', message: `→ Action: ${event.action}` }]);
            }
            else if (event.type === 'observation') {
              setLogs(prev => [...prev, { type: 'system', message: `✓ ${event.observation}` }]);
            }
            else if (event.type === 'final') {
              const data = event.data;
              setMessages(prev => [...prev, { 
                id: Date.now().toString(), 
                role: 'agent', 
                content: data.response || "No response provided." 
              }]);
              
              setInsights({
                status: data.status,
                product_area: data.product_area,
                confidence: data.confidence_score ? parseFloat(data.confidence_score) : 0,
                justification: data.justification
              });
            }
            else if (event.type === 'error') {
              throw new Error(event.message);
            }
          } catch (e) {
            console.error('Error parsing chunk', e);
          }
        }
      }

    } catch (error: any) {
      console.error(error);
      setMessages(prev => [...prev, { 
        id: Date.now().toString(), 
        role: 'agent', 
        content: `Error: ${error.message}` 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const [isDarkMode, setIsDarkMode] = useState(true);

  useEffect(() => {
    if (!isDarkMode) {
      document.body.classList.add('light-mode');
    } else {
      document.body.classList.remove('light-mode');
    }
  }, [isDarkMode]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--mouse-x', `${e.clientX}px`);
      document.documentElement.style.setProperty('--mouse-y', `${e.clientY}px`);
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <main className="app-container">
      {/* Chat Section */}
      <section className="glass-panel chat-section">
        <header className="chat-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 2rem' }}>
          <h1 style={{ 
            fontSize: '1.25rem', 
            fontWeight: 600, 
            color: 'var(--text-primary)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem'
          }}>
            Triage Agent
            <div className="info-trigger">
              <span className="info-icon">i</span>
              <div className="info-tooltip">
                <strong>AI Triage System</strong><br/>
                An intelligent support agent using ReAct reasoning and RAG to resolve tickets with human-like precision.
              </div>
            </div>
          </h1>
          <button 
            onClick={() => setIsDarkMode(!isDarkMode)}
            style={{ 
              background: 'var(--bg-tertiary)', 
              border: '1px solid var(--border-color)',
              borderRadius: '0.5rem',
              padding: '0.5rem 0.75rem',
              cursor: 'pointer',
              fontSize: '0.875rem',
              color: 'var(--text-primary)',
              fontWeight: 500,
              transition: 'all 0.2s'
            }}
          >
            {isDarkMode ? 'Light Mode' : 'Dark Mode'}
          </button>
        </header>
        
        <div className="messages-container">
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              {msg.content}
            </div>
          ))}
          {isLoading && (
            <div className="message agent">
              <div className="loading-dots">
                <div></div><div></div><div></div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Examples */}
        <div className="quick-examples">
          {[
            "I need a refund for my last payment",
            "My login is blocked on HackerRank",
            "What is the status of my Visa application?",
            "How do I reset my password?"
          ].map((ex, i) => (
            <button 
              key={i} 
              className="example-pill"
              onClick={() => {
                setInput(ex);
                // Optionally auto-submit:
                // handleSubmit(new Event('submit') as any);
              }}
            >
              {ex}
            </button>
          ))}
        </div>

        <form className="input-container" onSubmit={handleSubmit}>
          <textarea
            className="input-box"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe your issue..."
            rows={2}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <button 
            type="submit" 
            className="send-btn"
            disabled={!input.trim() || isLoading}
          >
            Send
          </button>
        </form>
      </section>

      {/* Insights Section */}
      <aside className="glass-panel insights-section">
        <h2>Live Insights</h2>
        
        {/* Thought Stream */}
        <div className="thought-stream-container">
          <div className="insight-label">Thought Stream</div>
          <div 
            className="thought-log" 
            ref={thoughtLogRef}
            onScroll={handleThoughtLogScroll}
          >
            {logs.length === 0 && !isLoading && (
              <div className="log-entry system">Ready for input...</div>
            )}
            {logs.map((log, i) => (
              <div key={i} className={`log-entry ${log.type}`}>
                {log.message}
              </div>
            ))}
            {isLoading && (
              <div className="log-entry system pulse">Thinking...</div>
            )}
          </div>
        </div>

        <hr className="divider" />

        {insights ? (
          <>
            <div className="insight-card">
              <div className="insight-label">Classification</div>
              <div className="insight-value">{insights.product_area || 'Unknown'}</div>
            </div>

            <div className="insight-card">
              <div className="insight-label">Status</div>
              <div className={`status-badge status-${insights.status.toLowerCase()}`}>
                {insights.status}
              </div>
            </div>

            <div className="insight-card">
              <div className="insight-label">Confidence Score</div>
              <div className="insight-value">{insights.confidence}%</div>
              <div className="confidence-bar-bg">
                <div 
                  className="confidence-bar-fill" 
                  style={{ width: `${insights.confidence}%` }}
                />
              </div>
            </div>

            <div className="insight-card">
              <div className="insight-label">Reasoning Justification</div>
              <div className="insight-value" style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--text-secondary)' }}>
                {insights.justification}
              </div>
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--text-secondary)', textAlign: 'center', marginTop: '2rem', fontSize: '0.875rem' }}>
            Submit an issue to see real-time triage insights.
          </div>
        )}
      </aside>
    </main>
  );
}
