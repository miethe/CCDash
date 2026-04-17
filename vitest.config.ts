import path from 'path';
import { configDefaults, defineConfig } from 'vitest/config';

export default defineConfig({
    resolve: {
        alias: {
            '@': path.resolve(__dirname, '.'),
        },
    },
    test: {
        exclude: [...configDefaults.exclude, '.claude/**'],
    },
});

