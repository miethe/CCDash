/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./node_modules/@miethe/ui/dist/**/*.js",
        "./components/**/*.{tsx,ts}",
        "./contexts/**/*.{tsx,ts}",
        "./services/**/*.ts",
        "./App.tsx",
        "./index.tsx",
    ],
    darkMode: ['class'],
    theme: {
    	extend: {
    		colors: {
    			slate: {
    				'850': '#1e293b',
    				'950': '#020617'
    			},
    			'app-background': 'hsl(var(--app-background))',
    			'app-foreground': 'hsl(var(--app-foreground))',
    			background: 'hsl(var(--background))',
    			foreground: 'hsl(var(--foreground))',
    			card: {
    				DEFAULT: 'hsl(var(--card))',
    				foreground: 'hsl(var(--card-foreground))'
    			},
    			popover: {
    				DEFAULT: 'hsl(var(--popover))',
    				foreground: 'hsl(var(--popover-foreground))'
    			},
    			primary: {
    				DEFAULT: 'hsl(var(--primary))',
    				foreground: 'hsl(var(--primary-foreground))'
    			},
    			secondary: {
    				DEFAULT: 'hsl(var(--secondary))',
    				foreground: 'hsl(var(--secondary-foreground))'
    			},
    			muted: {
    				DEFAULT: 'hsl(var(--muted))',
    				foreground: 'hsl(var(--muted-foreground))'
    			},
    			accent: {
    				DEFAULT: 'hsl(var(--accent))',
    				foreground: 'hsl(var(--accent-foreground))'
    			},
    			destructive: {
    				DEFAULT: 'hsl(var(--destructive))',
    				foreground: 'hsl(var(--destructive-foreground))'
    			},
    			panel: {
    				DEFAULT: 'hsl(var(--panel))',
    				foreground: 'hsl(var(--panel-foreground))',
    				border: 'hsl(var(--panel-border))'
    			},
    			sidebar: {
    				DEFAULT: 'hsl(var(--sidebar))',
    				foreground: 'hsl(var(--sidebar-foreground))',
    				accent: 'hsl(var(--sidebar-accent))',
    				border: 'hsl(var(--sidebar-border))'
    			},
    			surface: {
    				muted: 'hsl(var(--surface-muted))',
    				elevated: 'hsl(var(--surface-elevated))',
    				overlay: 'hsl(var(--surface-overlay))'
    			},
    			success: {
    				DEFAULT: 'hsl(var(--success))',
    				foreground: 'hsl(var(--success-foreground))',
    				border: 'hsl(var(--success-border))'
    			},
    			warning: {
    				DEFAULT: 'hsl(var(--warning))',
    				foreground: 'hsl(var(--warning-foreground))',
    				border: 'hsl(var(--warning-border))'
    			},
    			danger: {
    				DEFAULT: 'hsl(var(--danger))',
    				foreground: 'hsl(var(--danger-foreground))',
    				border: 'hsl(var(--danger-border))'
    			},
    			info: {
    				DEFAULT: 'hsl(var(--info))',
    				foreground: 'hsl(var(--info-foreground))',
    				border: 'hsl(var(--info-border))'
    			},
    			border: 'hsl(var(--border))',
    			input: 'hsl(var(--input))',
    			ring: 'hsl(var(--ring))',
    			selection: 'hsl(var(--selection))',
    			focus: 'hsl(var(--focus))',
    			hover: 'hsl(var(--hover))',
    			disabled: {
    				DEFAULT: 'hsl(var(--disabled))',
    				foreground: 'hsl(var(--disabled-foreground))'
    			},
    			chart: {
    				'1': 'hsl(var(--chart-1))',
    				'2': 'hsl(var(--chart-2))',
    				'3': 'hsl(var(--chart-3))',
    				'4': 'hsl(var(--chart-4))',
    				'5': 'hsl(var(--chart-5))',
    				grid: 'hsl(var(--chart-grid))',
    				axis: 'hsl(var(--chart-axis))',
    				tooltip: 'hsl(var(--chart-tooltip))',
    				'tooltip-foreground': 'hsl(var(--chart-tooltip-foreground))'
				},
				planning: {
					bg0: 'var(--bg-0)',
					bg1: 'var(--bg-1)',
					bg2: 'var(--bg-2)',
					bg3: 'var(--bg-3)',
					bg4: 'var(--bg-4)',
					line1: 'var(--line-1)',
					line2: 'var(--line-2)',
					ink0: 'var(--ink-0)',
					ink1: 'var(--ink-1)',
					ink2: 'var(--ink-2)',
					ink3: 'var(--ink-3)',
					spec: 'var(--spec)',
					spk: 'var(--spk)',
					prd: 'var(--prd)',
					plan: 'var(--plan)',
					prog: 'var(--prog)',
					ctx: 'var(--ctx)',
					trk: 'var(--trk)',
					rep: 'var(--rep)',
					ok: 'var(--ok)',
					warn: 'var(--warn)',
					err: 'var(--err)',
					info: 'var(--info)',
					mag: 'var(--mag)',
					opus: 'var(--m-opus)',
					sonnet: 'var(--m-sonnet)',
					haiku: 'var(--m-haiku)',
					brand: 'var(--brand)'
    				}
    			},
    			fontFamily: {
    				planningSans: ['var(--sans)', '-apple-system', 'system-ui', 'sans-serif'],
    				planningSerif: ['var(--serif)', 'Georgia', 'serif'],
    				planningMono: ['var(--mono)', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
    				mono: [
    					'ui-monospace',
    					'SFMono-Regular',
    				'Menlo',
    				'Monaco',
    				'Consolas',
    				'Liberation Mono',
    				'Courier New',
    				'monospace'
    			]
    		},
    		borderRadius: {
    			lg: 'var(--radius)',
    			md: 'calc(var(--radius) - 2px)',
    			sm: 'calc(var(--radius) - 4px)'
    		}
    	}
    },
    plugins: [require("tailwindcss-animate")],
};
