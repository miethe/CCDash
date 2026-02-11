/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./components/**/*.{tsx,ts}",
        "./contexts/**/*.{tsx,ts}",
        "./services/**/*.ts",
        "./App.tsx",
        "./index.tsx",
    ],
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                slate: {
                    850: '#1e293b',
                    950: '#020617',
                },
            },
            fontFamily: {
                mono: [
                    'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco',
                    'Consolas', 'Liberation Mono', 'Courier New', 'monospace',
                ],
            },
        },
    },
    plugins: [],
};
