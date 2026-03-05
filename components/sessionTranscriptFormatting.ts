export interface ParsedTagBlock {
    tag: string;
    value: string;
    raw: string;
    start: number;
    end: number;
}

export type TranscriptPresentationKind = 'command' | 'artifact' | 'action';
export type TranscriptMatchScope = 'command' | 'args' | 'command_and_args' | 'message';

export interface TranscriptFormattingMappingRule {
    id: string;
    mappingType: string;
    label: string;
    pattern: string;
    transcriptLabel?: string;
    transcriptKind?: TranscriptPresentationKind | string;
    icon?: string;
    color?: string;
    summaryTemplate?: string;
    extractPattern?: string;
    matchScope?: TranscriptMatchScope | string;
    platforms?: string[];
    enabled?: boolean;
    priority?: number;
}

export type TranscriptMessageKind =
    | 'plain'
    | 'claude-command'
    | 'claude-local-command-caveat'
    | 'claude-local-command-stdout'
    | 'mapped-command'
    | 'mapped-artifact'
    | 'mapped-action'
    | 'tagged';

export interface TranscriptFormattedMessage {
    engine: 'claude-code' | 'generic' | 'plain' | 'mapped';
    kind: TranscriptMessageKind;
    rawText: string;
    summary: string;
    tags: ParsedTagBlock[];
    text?: string;
    command?: {
        message?: string;
        name?: string;
        args?: string;
    };
    mapped?: {
        mappingId: string;
        mappingType: string;
        label: string;
        transcriptLabel: string;
        transcriptKind: TranscriptPresentationKind;
        icon?: string;
        color?: string;
        summaryTemplate?: string;
        command?: string;
        args?: string;
        matchText: string;
        groups: string[];
        namedGroups: Record<string, string>;
    };
}

const TAG_BLOCK_PATTERN = /<([a-z][a-z0-9-]*)>([\s\S]*?)<\/\1>/gi;
const COMMAND_NAME_TAG_PATTERN = /<command-name>\s*([^<\n]+)\s*<\/command-name>/gi;
const COMMAND_ARGS_TAG_PATTERN = /<command-args>\s*([\s\S]*?)\s*<\/command-args>/gi;
const SLASH_COMMAND_LINE_PATTERN = /^\s*(\/[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)?)\b(?:\s+([^\n]+))?\s*$/gim;
const SHELL_COMMAND_LINE_PATTERN = /^\s*(?:[$#>%]\s*)?([a-z0-9._-]+)(?:\s+(.+?))?\s*$/i;

const TITLE_CASE_PATTERN = /[-_]+/g;
const PLATFORM_SANITIZE_PATTERN = /[^a-z0-9_]+/g;
const TEMPLATE_VAR_PATTERN = /\{([a-zA-Z0-9_:-]+)\}/g;
const DEFAULT_TEMPLATE = '{label}: {match}';

const normalizeTagValue = (value: string): string => value.replace(/\r/g, '').trim();

const normalizePlatform = (value: string): string => {
    const raw = String(value || '').trim().toLowerCase().replace(/[-\s]+/g, '_');
    if (!raw) return '';
    if (raw === 'all' || raw === '*' || raw === 'any') return 'all';
    if (raw.includes('claude')) return 'claude_code';
    if (raw.includes('codex')) return 'codex';
    return raw.replace(PLATFORM_SANITIZE_PATTERN, '');
};

const normalizePlatforms = (values: unknown): string[] => {
    if (!Array.isArray(values)) return ['all'];
    const normalized = values
        .map(value => normalizePlatform(String(value || '')))
        .filter(Boolean);
    if (normalized.length === 0) return ['all'];
    if (normalized.includes('all')) return ['all'];
    return Array.from(new Set(normalized));
};

const mappingAppliesToPlatform = (rule: TranscriptFormattingMappingRule, platformType?: string): boolean => {
    const normalizedPlatform = normalizePlatform(String(platformType || ''));
    if (!normalizedPlatform) return true;
    const platforms = normalizePlatforms(rule.platforms);
    if (platforms.includes('all')) return true;
    return platforms.includes(normalizedPlatform);
};

const normalizeMappedKind = (
    mappingType: string,
    transcriptKind?: string,
): TranscriptPresentationKind => {
    const explicit = String(transcriptKind || '').trim().toLowerCase();
    if (explicit === 'artifact' || explicit === 'action' || explicit === 'command') {
        return explicit;
    }
    if (mappingType === 'artifact_call') return 'artifact';
    if (mappingType === 'action_call') return 'action';
    return 'command';
};

const mappedKindToMessageKind = (kind: TranscriptPresentationKind): TranscriptMessageKind => {
    if (kind === 'artifact') return 'mapped-artifact';
    if (kind === 'action') return 'mapped-action';
    return 'mapped-command';
};

const normalizeMatchScope = (scope: unknown): TranscriptMatchScope => {
    const normalized = String(scope || '').trim().toLowerCase();
    if (normalized === 'args') return 'args';
    if (normalized === 'command_and_args') return 'command_and_args';
    if (normalized === 'message') return 'message';
    return 'command';
};

const safeRegexSearch = (pattern: string, text: string): RegExpExecArray | null => {
    if (!pattern || !text) return null;
    try {
        const regex = new RegExp(pattern, 'i');
        return regex.exec(text);
    } catch {
        return null;
    }
};

const extractCommandInvocations = (content: string): Array<{ command: string; args: string }> => {
    const text = String(content || '').trim();
    if (!text) return [];

    COMMAND_NAME_TAG_PATTERN.lastIndex = 0;
    COMMAND_ARGS_TAG_PATTERN.lastIndex = 0;
    const tagCommands: string[] = [];
    let tagNameMatch = COMMAND_NAME_TAG_PATTERN.exec(text);
    while (tagNameMatch) {
        const commandName = String(tagNameMatch[1] || '').trim();
        if (commandName) {
            tagCommands.push(commandName);
        }
        tagNameMatch = COMMAND_NAME_TAG_PATTERN.exec(text);
    }
    if (tagCommands.length > 0) {
        const tagArgs: string[] = [];
        let tagArgsMatch = COMMAND_ARGS_TAG_PATTERN.exec(text);
        while (tagArgsMatch) {
            tagArgs.push(String(tagArgsMatch[1] || '').trim());
            tagArgsMatch = COMMAND_ARGS_TAG_PATTERN.exec(text);
        }
        return tagCommands.map((command, index) => ({
            command,
            args: tagArgs[index] || '',
        }));
    }

    const seen = new Set<string>();
    const invocations: Array<{ command: string; args: string }> = [];
    SLASH_COMMAND_LINE_PATTERN.lastIndex = 0;
    let slashMatch = SLASH_COMMAND_LINE_PATTERN.exec(text);
    while (slashMatch) {
        const command = String(slashMatch[1] || '').trim();
        const args = String(slashMatch[2] || '').trim();
        const key = `${command.toLowerCase()}::${args}`;
        if (command.startsWith('/') && !seen.has(key)) {
            seen.add(key);
            invocations.push({ command, args });
        }
        slashMatch = SLASH_COMMAND_LINE_PATTERN.exec(text);
    }

    if (invocations.length === 0) {
        const firstLine = text
            .replace(/^`+|`+$/g, '')
            .split(/\r?\n/)
            .map(line => line.trim())
            .find(Boolean);
        if (firstLine) {
            const shellMatch = SHELL_COMMAND_LINE_PATTERN.exec(firstLine);
            if (shellMatch) {
                const command = String(shellMatch[1] || '').trim();
                const args = String(shellMatch[2] || '').trim();
                if (command) {
                    invocations.push({ command, args });
                }
            }
        }
    }
    return invocations;
};

const renderSummaryTemplate = (template: string, context: Record<string, string>): string => {
    const base = String(template || '').trim() || DEFAULT_TEMPLATE;
    return base.replace(TEMPLATE_VAR_PATTERN, (_full, key: string) => {
        const value = context[key];
        return typeof value === 'string' ? value : '';
    }).trim();
};

const classifyMappedContent = (
    content: string,
    mappings: TranscriptFormattingMappingRule[] | undefined,
    platformType?: string,
): TranscriptFormattedMessage | null => {
    if (!Array.isArray(mappings) || mappings.length === 0) {
        return null;
    }
    const text = String(content || '').trim();
    if (!text) return null;

    const commands = extractCommandInvocations(text);
    const sorted = [...mappings]
        .filter(rule => rule && rule.enabled !== false && String(rule.pattern || '').trim())
        .sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0));

    for (const rule of sorted) {
        if (!mappingAppliesToPlatform(rule, platformType)) continue;
        const mappingType = String(rule.mappingType || '').trim().toLowerCase();
        const scope = normalizeMatchScope(rule.matchScope);
        const pattern = String(rule.extractPattern || rule.pattern || '').trim();
        const kind = normalizeMappedKind(mappingType, rule.transcriptKind);

        const candidates: Array<{ command: string; args: string; target: string }> = [];
        if (scope === 'message') {
            candidates.push({ command: '', args: '', target: text });
        } else {
            for (const invocation of commands) {
                let target = invocation.command;
                if (scope === 'args') {
                    target = invocation.args;
                } else if (scope === 'command_and_args') {
                    target = `${invocation.command} ${invocation.args}`.trim();
                } else if (scope === 'command' && invocation.command && !invocation.command.startsWith('/')) {
                    // Bash/tool commands are commonly represented as command + args in one line.
                    target = `${invocation.command} ${invocation.args}`.trim();
                }
                candidates.push({ command: invocation.command, args: invocation.args, target });
            }
        }

        for (const candidate of candidates) {
            const match = safeRegexSearch(pattern, candidate.target);
            if (!match) continue;

            const groupValues = match.slice(1).map(value => String(value || ''));
            const namedGroups: Record<string, string> = {};
            if (match.groups) {
                Object.entries(match.groups).forEach(([name, value]) => {
                    namedGroups[name] = String(value || '');
                });
            }
            const templateContext: Record<string, string> = {
                label: String(rule.transcriptLabel || rule.label || 'Mapped Event'),
                command: candidate.command,
                args: candidate.args,
                match: String(match[0] || ''),
                mapping: String(rule.label || ''),
            };
            groupValues.forEach((value, index) => {
                templateContext[`g${index + 1}`] = value;
            });
            Object.entries(namedGroups).forEach(([name, value]) => {
                templateContext[`group:${name}`] = value;
            });
            const summary = renderSummaryTemplate(
                String(rule.summaryTemplate || DEFAULT_TEMPLATE),
                templateContext,
            ) || templateContext.label;

            return {
                engine: 'mapped',
                kind: mappedKindToMessageKind(kind),
                rawText: content,
                summary,
                tags: parseTagBlocks(content),
                text: text,
                command: candidate.command
                    ? {
                        name: candidate.command,
                        args: candidate.args,
                    }
                    : undefined,
                mapped: {
                    mappingId: String(rule.id || ''),
                    mappingType,
                    label: String(rule.label || 'Mapped Event'),
                    transcriptLabel: String(rule.transcriptLabel || rule.label || 'Mapped Event'),
                    transcriptKind: kind,
                    icon: String(rule.icon || '').trim() || undefined,
                    color: String(rule.color || '').trim() || undefined,
                    summaryTemplate: String(rule.summaryTemplate || '').trim() || undefined,
                    command: candidate.command || undefined,
                    args: candidate.args || undefined,
                    matchText: String(match[0] || ''),
                    groups: groupValues,
                    namedGroups,
                },
            };
        }
    }
    return null;
};

const parseTagBlocks = (content: string): ParsedTagBlock[] => {
    const tags: ParsedTagBlock[] = [];
    TAG_BLOCK_PATTERN.lastIndex = 0;
    let match: RegExpExecArray | null = TAG_BLOCK_PATTERN.exec(content);
    while (match) {
        const raw = match[0];
        const start = match.index;
        const end = start + raw.length;
        tags.push({
            tag: (match[1] || '').toLowerCase(),
            value: normalizeTagValue(match[2] || ''),
            raw,
            start,
            end,
        });
        match = TAG_BLOCK_PATTERN.exec(content);
    }
    return tags;
};

const stripTagBlocks = (content: string, tags: ParsedTagBlock[]): string => {
    if (tags.length === 0) {
        return content.trim();
    }

    let cursor = 0;
    const fragments: string[] = [];

    for (const tag of tags) {
        if (tag.start > cursor) {
            fragments.push(content.slice(cursor, tag.start));
        }
        cursor = Math.max(cursor, tag.end);
    }

    if (cursor < content.length) {
        fragments.push(content.slice(cursor));
    }

    return fragments.join('\n').replace(/\n{3,}/g, '\n\n').trim();
};

const firstTagValue = (tags: ParsedTagBlock[], tagName: string): string | undefined => {
    const match = tags.find(tag => tag.tag === tagName);
    return match && match.value ? match.value : undefined;
};

const parseClaudeCodeMessage = (
    content: string,
    options?: ParseTranscriptMessageOptions,
): TranscriptFormattedMessage | null => {
    const tags = parseTagBlocks(content);
    if (tags.length === 0) {
        return null;
    }

    const commandMessage = firstTagValue(tags, 'command-message');
    const commandName = firstTagValue(tags, 'command-name');
    const commandArgs = firstTagValue(tags, 'command-args');
    const localCommandCaveat = firstTagValue(tags, 'local-command-caveat');
    const localCommandStdout = firstTagValue(tags, 'local-command-stdout');

    if (commandMessage || commandName || commandArgs !== undefined) {
        const mapped = classifyMappedContent(content, options?.mappings, options?.platformType);
        if (mapped) {
            return mapped;
        }
        const summary = commandName || commandMessage || 'Command Invocation';
        return {
            engine: 'claude-code',
            kind: 'claude-command',
            rawText: content,
            summary,
            tags,
            command: {
                message: commandMessage,
                name: commandName,
                args: commandArgs,
            },
        };
    }

    if (localCommandCaveat !== undefined) {
        return {
            engine: 'claude-code',
            kind: 'claude-local-command-caveat',
            rawText: content,
            summary: localCommandCaveat || 'Local command caveat',
            tags,
            text: localCommandCaveat,
        };
    }

    if (localCommandStdout !== undefined) {
        return {
            engine: 'claude-code',
            kind: 'claude-local-command-stdout',
            rawText: content,
            summary: localCommandStdout || 'Local command output',
            tags,
            text: localCommandStdout,
        };
    }

    return null;
};

const parseGenericTaggedMessage = (content: string): TranscriptFormattedMessage | null => {
    const tags = parseTagBlocks(content);
    if (tags.length === 0 || content.includes('```')) {
        return null;
    }

    const totalTagLength = tags.reduce((sum, tag) => sum + tag.raw.length, 0);
    const normalizedLength = Math.max(content.trim().length, 1);
    const tagCoverage = totalTagLength / normalizedLength;
    const hasSignalTagName = tags.some(tag => tag.tag.includes('-'));
    if (!hasSignalTagName || tagCoverage < 0.45) {
        return null;
    }

    const stripped = stripTagBlocks(content, tags);
    return {
        engine: 'generic',
        kind: 'tagged',
        rawText: content,
        summary: stripped || `${tags.length} tagged blocks`,
        tags,
        text: stripped || undefined,
    };
};

export interface ParseTranscriptMessageOptions {
    mappings?: TranscriptFormattingMappingRule[];
    platformType?: string;
}

export const parseTranscriptMessage = (
    content: string,
    options?: ParseTranscriptMessageOptions,
): TranscriptFormattedMessage => {
    const claude = parseClaudeCodeMessage(content, options);
    if (claude) {
        return claude;
    }

    const mapped = classifyMappedContent(content, options?.mappings, options?.platformType);
    if (mapped) {
        return mapped;
    }

    const generic = parseGenericTaggedMessage(content);
    if (generic) {
        return generic;
    }

    const cleanText = content.trim();
    return {
        engine: 'plain',
        kind: 'plain',
        rawText: content,
        summary: cleanText || '(empty message)',
        tags: [],
        text: cleanText,
    };
};

export const getReadableTagName = (tagName: string): string =>
    tagName
        .replace(TITLE_CASE_PATTERN, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .replace(/\b\w/g, letter => letter.toUpperCase());
