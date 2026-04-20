// Tweaks panel — in-design controls. Floats bottom-right. Shows only when activated.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "comfortable",
  "graphView": "dag",
  "mode": "orchestrator",
  "accent": "cyan",
  "liveAgents": true,
  "showCompleted": true
}/*EDITMODE-END*/;

const ACCENTS = {
  cyan:   'oklch(75% 0.14 195)',
  violet: 'oklch(72% 0.16 290)',
  amber:  'oklch(80% 0.14 70)',
  green:  'oklch(74% 0.15 150)',
  rose:   'oklch(72% 0.16 10)',
};

function TweaksPanel({ tweaks, setTweak, onClose }) {
  return (
    <div style={{
      position: 'fixed', bottom: 16, right: 16, zIndex: 60,
      width: 280,
      background: 'var(--bg-1)',
      border: '1px solid var(--line-2)',
      borderRadius: 'var(--radius)',
      boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
      overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid var(--line-1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--brand)' }}>{Icons.settings}</span>
          <span style={{ fontSize: 12, fontWeight: 600 }}>Tweaks</span>
        </div>
        <button className="btn btn-ghost" onClick={onClose} style={{ padding: 4 }}>{Icons.x}</button>
      </div>
      <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Group label="Density">
          <Seg options={['compact', 'comfortable']} value={tweaks.density} onChange={v => setTweak('density', v)} />
        </Group>
        <Group label="Graph view">
          <Seg options={['dag', 'swimlane', 'list']} value={tweaks.graphView} onChange={v => setTweak('graphView', v)} />
        </Group>
        <Group label="Mode">
          <Seg options={['orchestrator', 'author', 'operator']} value={tweaks.mode} onChange={v => setTweak('mode', v)} />
        </Group>
        <Group label="Accent">
          <div style={{ display: 'flex', gap: 6 }}>
            {Object.entries(ACCENTS).map(([k, v]) => (
              <button key={k}
                onClick={() => { setTweak('accent', k); document.documentElement.style.setProperty('--brand', v); }}
                style={{
                  width: 24, height: 24, borderRadius: 6,
                  background: v, cursor: 'pointer',
                  border: tweaks.accent === k ? '2px solid var(--ink-0)' : '1px solid var(--line-2)',
                }} />
            ))}
          </div>
        </Group>
        <Group label="Live agent activity">
          <Toggle value={tweaks.liveAgents} onChange={v => setTweak('liveAgents', v)} />
        </Group>
        <Group label="Show completed features">
          <Toggle value={tweaks.showCompleted} onChange={v => setTweak('showCompleted', v)} />
        </Group>
      </div>
    </div>
  );
}

function Group({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div className="caps" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{label}</div>
      {children}
    </div>
  );
}

function Seg({ options, value, onChange }) {
  return (
    <div style={{ display: 'flex', background: 'var(--bg-0)', border: '1px solid var(--line-1)', borderRadius: 6, padding: 2 }}>
      {options.map(o => (
        <button key={o} onClick={() => onChange(o)} style={{
          flex: 1, padding: '5px 6px', fontSize: 11,
          background: value === o ? 'var(--bg-3)' : 'transparent',
          color: value === o ? 'var(--ink-0)' : 'var(--ink-2)',
          border: 'none', borderRadius: 4, cursor: 'pointer', textTransform: 'capitalize',
          fontFamily: 'inherit',
        }}>
          {o}
        </button>
      ))}
    </div>
  );
}

function Toggle({ value, onChange }) {
  return (
    <button onClick={() => onChange(!value)} style={{
      width: 40, height: 22, borderRadius: 999,
      background: value ? 'color-mix(in oklab, var(--brand) 50%, var(--bg-3))' : 'var(--bg-3)',
      border: '1px solid var(--line-1)', cursor: 'pointer', position: 'relative', padding: 0,
    }}>
      <span style={{
        position: 'absolute', top: 2, left: value ? 20 : 2,
        width: 16, height: 16, borderRadius: 999,
        background: 'var(--ink-0)', transition: 'left .15s',
      }} />
    </button>
  );
}

Object.assign(window, { TweaksPanel, TWEAK_DEFAULTS });
