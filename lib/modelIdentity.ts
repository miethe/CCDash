export interface ModelDescriptor {
  raw: string;
  displayName?: string;
  provider?: string;
  family?: string;
  version?: string;
}

const titleCase = (value: string): string =>
  value
    .split(/\s+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export const formatModelDisplayName = (rawModel: string, provided?: string): string => {
  const providedLabel = (provided || '').trim();
  if (providedLabel) return providedLabel;

  const raw = (rawModel || '').trim();
  if (!raw) return 'Unknown Model';
  const tokens = raw.toLowerCase().split(/[-_\s]+/).filter(Boolean);
  if (tokens.length === 0) return raw;

  const provider = tokens[0] === 'claude'
    ? 'Claude'
    : tokens[0] === 'gpt' || tokens[0] === 'openai'
      ? 'OpenAI'
      : tokens[0] === 'gemini'
        ? 'Gemini'
        : titleCase(tokens[0]);
  const family = tokens[1] ? titleCase(tokens[1]) : '';

  let version = '';
  const nums = tokens.slice(2).filter(token => /^\d+$/.test(token));
  if (nums.length >= 2) {
    version = `${nums[0]}.${nums[1]}`;
  } else if (nums.length === 1) {
    version = nums[0];
  }

  if (family && version) return `${provider} ${family} ${version}`;
  if (family) return `${provider} ${family}`;
  return provider || raw;
};

export const extractModelIdentity = (
  model: ModelDescriptor,
): { displayName: string; provider: string; family: string; version: string } => {
  const displayName = formatModelDisplayName(model.raw, model.displayName);
  const raw = (model.raw || '').toLowerCase();
  const providedProvider = (model.provider || '').trim();
  const providedFamily = (model.family || '').trim();
  const providedVersion = (model.version || '').trim();

  const provider = providedProvider || (
    raw.includes('claude')
      ? 'Claude'
      : raw.includes('gpt') || raw.includes('openai')
        ? 'OpenAI'
        : raw.includes('gemini')
          ? 'Gemini'
          : displayName.split(/\s+/)[0] || 'Model'
  );

  let family = providedFamily;
  if (!family) {
    if (raw.includes('opus')) family = 'Opus';
    else if (raw.includes('sonnet')) family = 'Sonnet';
    else if (raw.includes('haiku')) family = 'Haiku';
    else if (raw.includes('gpt-5')) family = 'GPT-5';
    else if (raw.includes('gpt-4o')) family = 'GPT-4o';
    else if (raw.includes('gpt-4')) family = 'GPT-4';
    else if (raw.includes('gemini')) family = 'Gemini';
  }

  let version = providedVersion;
  if (!version) {
    const claudeNamed = raw.match(/(?:opus|sonnet|haiku)-(\d+)-(\d+)/);
    const claudeNumeric = raw.match(/claude-(\d+)-(\d+)-(?:opus|sonnet|haiku)/);
    const gpt = raw.match(/gpt-(\d+(?:\.\d+)?[a-z0-9-]*)/);
    if (claudeNumeric) version = `${claudeNumeric[1]}.${claudeNumeric[2]}`;
    else if (claudeNamed) version = `${claudeNamed[1]}.${claudeNamed[2]}`;
    else if (gpt) version = gpt[1].toUpperCase();
  }

  if (!family) family = provider;
  if (!version && providedVersion) version = providedVersion;

  return {
    displayName,
    provider,
    family,
    version,
  };
};
