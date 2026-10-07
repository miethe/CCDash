import path from 'path';
import { configDefaults, defineConfig } from 'vitest/config';

export default defineConfig({
    resolve: {
        alias: {
            '@': path.resolve(__dirname, '.'),
        },
    },
    test: {
        // .claude/** and .codex/** hold agent tooling, not CCDash tests;
        // .codex/{agents,skills} are tracked symlinks into ../skillmeat/.claude/*.
        exclude: [...configDefaults.exclude, '.claude/**', '.codex/**', 'examples/**'],
        server: {
            deps: {
                // @miethe/ui ships extensionless ESM imports (tsc emit); inline it
                // through Vite's resolver instead of Node's native ESM loader.
                inline: [/@miethe\/ui/],
            },
        },
    },
});

