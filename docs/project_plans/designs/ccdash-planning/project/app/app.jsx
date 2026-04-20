// Main app shell. Three-column layout: app rail · main canvas · (drawer).
// Main canvas: Planning Deck header → metrics strip → Triage + Lineage graph → roster.

const { useState, useEffect, useMemo, useCallback } = React;

function App() {
  const [tweaks, setTweaks] = useState(window.TWEAK_DEFAULTS);
  const [tweaksOpen, setTweaksOpen] = useState(false);
  const [editModeAvailable, setEditModeAvailable] = useState(false);
  const [selectedFeatureId, setSelectedFeatureId] = useState(null);
  const [selectedArtifact, setSelectedArtifact] = useState(null); // { feature, kind }
  const [focusKind, setFocusKind] = useState(null); // which section to scroll to in detail
  const [toast, setToast] = useState(null);

  const runToast = (label) => {
    setToast(label);
    setTimeout(() => setToast(null), 2400);
  };
  const handleExec = (payload) => {
    const { kind } = payload;
    const label =
      kind === 'feature' ? `▶ dispatching feature "${payload.feature.title}"`
      : kind === 'phase'  ? `▶ running Phase ${String(payload.phase.n).padStart(2,'0')} — ${payload.phase.name}`
      : kind === 'batch'  ? `▶ running Batch ${payload.batch} of Phase ${String(payload.phase.n).padStart(2,'0')} in parallel`
      : kind === 'task'   ? `▶ queued ${payload.task.id} — ${payload.task.title}`
      : kind === 'spike'  ? `▶ running SPIKE ${payload.spike.id}`
      : `▶ executing`;
    runToast(label);
  };

  // Tweaks protocol
  useEffect(() => {
    function onMsg(e) {
      if (e.data?.type === '__activate_edit_mode') setTweaksOpen(true);
      if (e.data?.type === '__deactivate_edit_mode') setTweaksOpen(false);
    }
    window.addEventListener('message', onMsg);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    setEditModeAvailable(true);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  const setTweak = useCallback((key, value) => {
    setTweaks(prev => {
      const next = { ...prev, [key]: value };
      window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { [key]: value } }, '*');
      return next;
    });
  }, []);

  // Apply density
  useEffect(() => {
    document.body.className = `density-${tweaks.density}`;
  }, [tweaks.density]);

  // Apply accent on load
  useEffect(() => {
    const accents = { cyan: 'oklch(75% 0.14 195)', violet: 'oklch(72% 0.16 290)', amber: 'oklch(80% 0.14 70)', green: 'oklch(74% 0.15 150)', rose: 'oklch(72% 0.16 10)' };
    if (accents[tweaks.accent]) document.documentElement.style.setProperty('--brand', accents[tweaks.accent]);
  }, [tweaks.accent]);

  const { FEATURES, buildTriage, buildMetrics, LIVE_AGENTS } = window.APP_DATA;
  const triage = useMemo(() => buildTriage(), []);
  const metrics = useMemo(() => buildMetrics(), []);

  const visibleFeatures = useMemo(() => {
    return FEATURES.filter(f => tweaks.showCompleted || f.effective !== 'completed');
  }, [tweaks.showCompleted]);

  const selectedFeature = FEATURES.find(f => f.id === selectedFeatureId) || null;

  return (
    <div style={{ minHeight: '100vh', display: 'flex' }}>
      <AppRail />
      <main style={{ flex: 1, minWidth: 0, padding: '22px 28px 80px 28px', maxWidth: 1680 }}>
        <TopBar metrics={metrics} liveAgents={LIVE_AGENTS} liveEnabled={tweaks.liveAgents} />

        <div style={{ marginTop: 22 }}>
          <HeroHeader metrics={metrics} />
        </div>

        {/* Metrics strip */}
        <div style={{ marginTop: 22, display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 10 }}>
          <MetricTile label="Features" value={metrics.total} />
          <MetricTile label="Active" value={metrics.active} accent="var(--plan)" />
          <MetricTile label="Blocked" value={metrics.blocked} accent="var(--err)" />
          <MetricTile label="Stale" value={metrics.stale} accent="var(--warn)" />
          <MetricTile label="Mismatches" value={metrics.mismatch} accent="var(--mag)" />
          <MetricTile label="Completed" value={metrics.completed} accent="var(--ok)" />
        </div>

        {/* Artifact composition chips */}
        <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="caps" style={{ fontSize: 10, color: 'var(--ink-3)', marginRight: 6 }}>Artifacts</span>
          {Object.entries(metrics.counts).map(([k, v]) => (
            <span key={k} className="chip mono" style={{
              borderColor: `color-mix(in oklab, var(--${k}) 35%, var(--line-1))`,
              color: 'var(--ink-1)',
            }}>
              <span style={{ color: `var(--${k})` }}>{window.APP_DATA.ARTIFACTS[k].glyph}</span>
              {window.APP_DATA.ARTIFACTS[k].short}
              <span className="tnum" style={{ color: 'var(--ink-2)' }}>{v}</span>
            </span>
          ))}
          <span style={{ flex: 1 }} />
          <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>
            corpus · {metrics.corpus.completed} completed · {metrics.corpus.schemas} schemas · {metrics.corpus.agents}+ agents
          </span>
        </div>

        {/* Two-up: triage + live roster */}
        <div style={{ marginTop: 24, display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16 }}>
          <div>
            <SectionHeader eyebrow="01 / Triage" title="What needs your attention" glyph="◇">
              <button className="btn btn-ghost" style={{ fontSize: 11 }}>{Icons.refresh} Rescan</button>
            </SectionHeader>
            <TriageInbox items={triage} onSelectFeature={setSelectedFeatureId} />
          </div>
          <div>
            <SectionHeader eyebrow="02 / Orchestra" title="Live agent roster" glyph="◉">
              <span className="chip mono" style={{ fontSize: 10, color: tweaks.liveAgents ? 'var(--ok)' : 'var(--ink-3)', borderColor: tweaks.liveAgents ? 'color-mix(in oklab, var(--ok) 40%, var(--line-1))' : 'var(--line-1)' }}>
                <span className="dot" style={{ background: tweaks.liveAgents ? 'var(--ok)' : 'var(--ink-3)' }} />
                {tweaks.liveAgents ? 'live' : 'paused'}
              </span>
            </SectionHeader>
            <AgentRoster enabled={tweaks.liveAgents} />
          </div>
        </div>

        {/* Planning graph — hero */}
        <div style={{ marginTop: 32 }}>
          <SectionHeader eyebrow="03 / Lineage" title="The Planning Graph" glyph="▲">
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-ghost" style={{ fontSize: 11 }}>{Icons.filter} All categories</button>
              <button className="btn" style={{ fontSize: 11 }}>{Icons.plus} New feature</button>
            </div>
          </SectionHeader>
          <PlanningGraph
            features={visibleFeatures}
            onSelectFeature={setSelectedFeatureId}
            onSelectNode={({ feature, kind, doc }) => { setSelectedFeatureId(feature.id); setSelectedArtifact({ feature, kind, doc }); setFocusKind(kind); }}
            selectedFeatureId={selectedFeatureId}
            viewMode={tweaks.graphView}
          />
          <Legend />
        </div>
      </main>

      {/* Detail drawer */}
      {selectedFeature && (
        <FeatureDetail
          feature={selectedFeature}
          onClose={() => { setSelectedFeatureId(null); setSelectedArtifact(null); setFocusKind(null); }}
          onOpenArtifact={(kind) => { setSelectedArtifact({ feature: selectedFeature, kind }); setFocusKind(kind); }}
          focusKind={focusKind}
          onExec={handleExec}
        />
      )}

      {/* Tweaks */}
      {tweaksOpen && (
        <TweaksPanel tweaks={tweaks} setTweak={setTweak} onClose={() => setTweaksOpen(false)} />
      )}

      {/* Manual tweaks toggle (for viewing without the host toolbar) */}
      {!tweaksOpen && (
        <button onClick={() => setTweaksOpen(true)} style={{
          position: 'fixed', bottom: 16, right: 16, zIndex: 40,
          width: 36, height: 36, borderRadius: 18,
          background: 'var(--bg-1)', border: '1px solid var(--line-2)',
          color: 'var(--ink-2)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} title="Tweaks">
          {Icons.settings}
        </button>
      )}

      {/* Exec toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--bg-1)', border: '1px solid color-mix(in oklab, var(--brand) 45%, var(--line-2))',
          color: 'var(--ink-0)', padding: '10px 16px', borderRadius: 6,
          fontSize: 12, fontFamily: 'var(--mono)',
          boxShadow: '0 14px 40px rgba(0,0,0,0.45)', zIndex: 60,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span className="dot" style={{ background: 'var(--brand)' }} />
          {toast}
        </div>
      )}
    </div>
  );
}

function AppRail() {
  const items = [
    { glyph: '◎', label: 'Dashboard' },
    { glyph: '▲', label: 'Planning', active: true },
    { glyph: '●', label: 'Sessions' },
    { glyph: '▣', label: 'Analytics' },
    { glyph: '◆', label: 'Codebase' },
    { glyph: '◇', label: 'Trackers' },
  ];
  return (
    <aside style={{
      width: 64, background: 'var(--bg-1)', borderRight: '1px solid var(--line-1)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '18px 0', gap: 4,
      position: 'sticky', top: 0, height: '100vh',
    }}>
      {/* Wordmark */}
      <div style={{
        width: 36, height: 36, borderRadius: 10,
        background: 'linear-gradient(135deg, color-mix(in oklab, var(--brand) 80%, transparent), color-mix(in oklab, var(--prog) 60%, transparent))',
        display: 'grid', placeItems: 'center',
        fontFamily: 'var(--serif)', fontSize: 17, fontWeight: 600, color: 'var(--bg-0)',
        letterSpacing: '-0.03em', marginBottom: 14,
      }}>cc</div>
      {items.map((it, i) => (
        <button key={i} title={it.label}
          style={{
            width: 44, height: 44, borderRadius: 10,
            background: it.active ? 'color-mix(in oklab, var(--brand) 16%, var(--bg-2))' : 'transparent',
            border: it.active ? '1px solid color-mix(in oklab, var(--brand) 32%, var(--line-1))' : '1px solid transparent',
            color: it.active ? 'var(--brand)' : 'var(--ink-2)',
            fontSize: 16, cursor: 'pointer', display: 'grid', placeItems: 'center',
          }}>
          {it.glyph}
        </button>
      ))}
    </aside>
  );
}

function TopBar({ metrics, liveAgents, liveEnabled }) {
  const running = liveAgents.filter(a => a.state === 'running').length;
  const thinking = liveAgents.filter(a => a.state === 'thinking').length;
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <nav style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ color: 'var(--ink-3)' }}>CCDash</span>
          <span style={{ color: 'var(--ink-4)' }}>/</span>
          <span style={{ color: 'var(--ink-2)' }}>CCDash · Planning</span>
          <span style={{ color: 'var(--ink-4)' }}>/</span>
          <span style={{ color: 'var(--ink-0)' }}>Planning Deck</span>
        </nav>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div className="mono" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--ink-2)', padding: '5px 10px', background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 6 }}>
          <span style={{ color: liveEnabled ? 'var(--ok)' : 'var(--ink-3)' }} className={liveEnabled ? '' : ''}>●</span>
          {liveEnabled ? 'live' : 'idle'}
          <span style={{ color: 'var(--ink-3)' }}>·</span>
          {running} running
          <span style={{ color: 'var(--ink-3)' }}>·</span>
          {thinking} thinking
        </div>
        <button className="btn"><span style={{ color: 'var(--ink-3)' }}>⌘K</span> Search</button>
        <button className="btn btn-primary">{Icons.plus} New spec</button>
      </div>
    </div>
  );
}

function HeroHeader({ metrics }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 32, borderBottom: '1px solid var(--line-1)', paddingBottom: 20 }}>
      <div>
        <div className="caps" style={{ fontSize: 10.5, color: 'var(--ink-3)', marginBottom: 10 }}>
          ccdash · planning — ai-native sdlc · active project
        </div>
        <h1 className="serif" style={{
          margin: 0, fontSize: 44, fontWeight: 400,
          letterSpacing: '-0.025em', lineHeight: 1.05, color: 'var(--ink-0)',
          fontStyle: 'italic',
        }}>
          The Planning Deck.
        </h1>
        <p style={{ margin: '8px 0 0', fontSize: 13.5, color: 'var(--ink-2)', maxWidth: 640 }}>
          Eight artifact types. {metrics.corpus.agents}+ specialized agents. One surface to orchestrate
          them — from idea through retrospective, with token-disciplined delegation at every step.
        </p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
        <div className="mono tnum" style={{ fontSize: 11, color: 'var(--ink-3)' }}>
          {new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })} · {metrics.corpus.contextPerPhase} ctx/phase
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Spark data={[4, 6, 5, 7, 10, 8, 12, 11, 14, 13, 15, 12, 16, 18]} color="var(--brand)" w={120} h={28} />
          <span className="mono tnum" style={{ fontSize: 11, color: 'var(--ok)' }}>+{metrics.corpus.tokensSaved}% tokens saved</span>
        </div>
      </div>
    </div>
  );
}

function AgentRoster({ enabled }) {
  const { LIVE_AGENTS, AGENTS } = window.APP_DATA;
  return (
    <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '14px 1fr auto auto', padding: '8px 14px', borderBottom: '1px solid var(--line-1)', gap: 10 }}>
        <span />
        <span className="caps" style={{ fontSize: 9.5, color: 'var(--ink-3)' }}>agent</span>
        <span className="caps" style={{ fontSize: 9.5, color: 'var(--ink-3)' }}>task</span>
        <span className="caps" style={{ fontSize: 9.5, color: 'var(--ink-3)' }}>since</span>
      </div>
      {LIVE_AGENTS.map((l, i) => {
        const a = AGENTS[l.agent] || {};
        const color = l.state === 'running' ? 'var(--ok)'
                    : l.state === 'thinking' ? 'var(--info)'
                    : l.state === 'queued' ? 'var(--warn)'
                    : 'var(--ink-3)';
        return (
          <div key={i} style={{
            display: 'grid', gridTemplateColumns: '14px 1fr auto auto',
            gap: 10, alignItems: 'center',
            padding: '10px 14px',
            borderBottom: i < LIVE_AGENTS.length - 1 ? '1px solid var(--line-1)' : 'none',
            opacity: enabled ? 1 : 0.5,
          }}>
            <span className="dot" style={{
              background: color, width: 8, height: 8,
              boxShadow: enabled && (l.state === 'running' || l.state === 'thinking') ? `0 0 8px ${color}` : 'none',
            }} />
            <div style={{ minWidth: 0 }}>
              <div className="mono" style={{ fontSize: 11.5, color: 'var(--ink-0)' }}>{l.agent}</div>
              <div style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>
                <span className="mono">{a.model || '—'}</span> · {a.tier || '—'}
              </div>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-1)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {l.task}
            </div>
            <div className="mono tnum" style={{ fontSize: 10.5, color: 'var(--ink-3)', minWidth: 48, textAlign: 'right' }}>{l.since}</div>
          </div>
        );
      })}
    </div>
  );
}

function Legend() {
  const { ARTIFACTS } = window.APP_DATA;
  return (
    <div style={{ marginTop: 10, display: 'flex', gap: 16, alignItems: 'center', fontSize: 11, color: 'var(--ink-3)', flexWrap: 'wrap' }}>
      <span className="caps" style={{ fontSize: 10 }}>legend</span>
      {Object.values(ARTIFACTS).map(a => (
        <span key={a.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, background: a.color, borderRadius: 2 }} />
          {a.label}
        </span>
      ))}
      <span style={{ flex: 1 }} />
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <svg width="28" height="10"><path d="M0 5 L28 5" stroke="var(--brand)" strokeWidth="1.2" strokeDasharray="4 6" className="flow"/></svg>
        active edge
      </span>
    </div>
  );
}

window.App = App;
