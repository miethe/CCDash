import { ProjectTestConfig, ProjectTestPlatformConfig, TestPlatformId } from '../types';

const buildPlatform = (
  id: TestPlatformId,
  enabled: boolean,
  resultsDir: string,
  watch: boolean,
  patterns: string[],
): ProjectTestPlatformConfig => ({
  id,
  enabled,
  resultsDir,
  watch,
  patterns,
});

export const DEFAULT_TEST_CONFIG: ProjectTestConfig = {
  flags: {
    testVisualizerEnabled: true,
    integritySignalsEnabled: true,
    liveTestUpdatesEnabled: true,
    semanticMappingEnabled: true,
  },
  platforms: [
    buildPlatform('pytest', true, 'test-results', true, ['**/*.xml', '**/junit*.xml', '**/pytest*.xml']),
    buildPlatform('jest', false, 'skillmeat/web', true, ['**/jest-results*.json', '**/coverage/coverage-final.json']),
    buildPlatform('playwright', false, 'skillmeat/web/test-results', true, ['**/results.json']),
    buildPlatform('coverage', false, '.', false, ['**/coverage.xml', '**/coverage.json', '**/lcov.info', '**/coverage-final.json']),
    buildPlatform('benchmark', false, '.', false, ['**/benchmark*_results.json', '**/benchmark*.json']),
    buildPlatform('lighthouse', false, 'skillmeat/web/lighthouse-reports', false, ['**/*.json', '**/*.html']),
    buildPlatform('locust', false, '.', false, ['**/locust_report.html', '**/locust_results*.csv']),
    buildPlatform('triage', false, '.', false, ['**/test-failures.json', '**/test-failures-summary.txt', '**/test-failures.md']),
  ],
  autoSyncOnStartup: true,
  maxFilesPerScan: 500,
  maxParseConcurrency: 4,
  instructionProfile: 'skillmeat',
  instructionNotes: '',
};

const cloneConfig = (cfg: ProjectTestConfig): ProjectTestConfig => ({
  ...cfg,
  flags: { ...cfg.flags },
  platforms: cfg.platforms.map(platform => ({
    ...platform,
    patterns: [...platform.patterns],
  })),
});

export const defaultTestConfig = (): ProjectTestConfig => cloneConfig(DEFAULT_TEST_CONFIG);

export const ensureProjectTestConfig = (value?: Partial<ProjectTestConfig> | null): ProjectTestConfig => {
  const cfg = value || {};
  const merged = cloneConfig(DEFAULT_TEST_CONFIG);
  merged.flags = {
    ...merged.flags,
    ...(cfg.flags || {}),
  };
  if (Array.isArray(cfg.platforms)) {
    const byId = new Map(cfg.platforms.filter(Boolean).map(platform => [platform.id, platform]));
    merged.platforms = merged.platforms.map(platform => {
      const current = byId.get(platform.id);
      if (!current) return platform;
      return {
        ...platform,
        ...current,
        patterns: Array.isArray(current.patterns) && current.patterns.length > 0
          ? current.patterns
          : platform.patterns,
      };
    });
  }
  merged.autoSyncOnStartup = cfg.autoSyncOnStartup ?? merged.autoSyncOnStartup;
  merged.maxFilesPerScan = cfg.maxFilesPerScan ?? merged.maxFilesPerScan;
  merged.maxParseConcurrency = cfg.maxParseConcurrency ?? merged.maxParseConcurrency;
  merged.instructionProfile = cfg.instructionProfile ?? merged.instructionProfile;
  merged.instructionNotes = cfg.instructionNotes ?? merged.instructionNotes;
  return merged;
};
