// Triage inbox — actionable surface for mismatches, blockers, stale specs, ready-to-promote.

function TriageInbox({ items, onSelectFeature }) {
  const [filter, setFilter] = React.useState('all');

  const filtered = React.useMemo(() => {
    if (filter === 'all') return items;
    return items.filter(i => i.kind === filter);
  }, [items, filter]);

  const tabs = [
    { key: 'all', label: 'All', count: items.length },
    { key: 'blocked', label: 'Blocked', count: items.filter(i => i.kind === 'blocked').length },
    { key: 'mismatch', label: 'Mismatches', count: items.filter(i => i.kind === 'mismatch').length },
    { key: 'stale', label: 'Stale', count: items.filter(i => i.kind === 'stale').length },
    { key: 'ready', label: 'Ready to promote', count: items.filter(i => i.kind === 'ready').length },
  ];

  return (
    <div className="panel" style={{ overflow: 'hidden' }}>
      {/* Tab strip */}
      <div style={{ display: 'flex', gap: 2, padding: '10px 14px 0 14px', borderBottom: '1px solid var(--line-1)' }}>
        {tabs.map(t => (
          <button key={t.key}
            onClick={() => setFilter(t.key)}
            style={{
              padding: '8px 12px',
              fontSize: 12,
              fontWeight: 500,
              background: 'transparent',
              border: 'none',
              color: filter === t.key ? 'var(--ink-0)' : 'var(--ink-2)',
              borderBottom: filter === t.key ? '2px solid var(--brand)' : '2px solid transparent',
              marginBottom: -1,
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6,
              fontFamily: 'inherit',
            }}>
            {t.label}
            <span className="tnum mono" style={{
              padding: '1px 6px', borderRadius: 8, fontSize: 10,
              background: filter === t.key ? 'color-mix(in oklab, var(--brand) 20%, transparent)' : 'var(--bg-3)',
              color: filter === t.key ? 'var(--brand)' : 'var(--ink-2)',
            }}>
              {t.count}
            </span>
          </button>
        ))}
      </div>

      {/* Items */}
      <div style={{ maxHeight: 380, overflow: 'auto' }}>
        {filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
            <div style={{ fontSize: 24, marginBottom: 8, color: 'var(--ok)' }}>✓</div>
            Nothing to triage.
          </div>
        ) : (
          filtered.map(it => <TriageRow key={it.id} item={it} onSelectFeature={onSelectFeature} />)
        )}
      </div>
    </div>
  );
}

function TriageRow({ item, onSelectFeature }) {
  const severityColor = {
    high: 'var(--err)',
    medium: 'var(--warn)',
    low: 'var(--info)',
    info: 'var(--spec)',
  }[item.severity];

  const kindLabel = {
    blocked: 'BLOCKED',
    mismatch: 'MISMATCH',
    stale: 'STALE',
    ready: 'READY',
  }[item.kind];

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '6px 110px 1fr auto',
      alignItems: 'center',
      gap: 14,
      padding: '12px 14px',
      borderBottom: '1px solid var(--line-1)',
    }}>
      <div style={{ width: 3, height: 24, background: severityColor, borderRadius: 2 }} />
      <div>
        <div className="mono caps" style={{ fontSize: 10, color: severityColor, letterSpacing: 0.12 + 'em' }}>{kindLabel}</div>
        <div className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.feature.slug}>
          {item.feature.slug}
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        <button onClick={() => onSelectFeature?.(item.feature.id)} style={{
          background: 'none', border: 'none', padding: 0, color: 'var(--ink-0)',
          fontSize: 13, fontWeight: 500, textAlign: 'left', cursor: 'pointer',
          fontFamily: 'inherit', maxWidth: '100%',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block',
        }}>
          {item.title}
        </button>
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.reason}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button className="btn" style={{ fontSize: 11, padding: '4px 8px' }}>{item.actions[0]}</button>
        <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }}>{Icons.chevron}</button>
      </div>
    </div>
  );
}

Object.assign(window, { TriageInbox });
