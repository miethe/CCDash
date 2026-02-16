export interface ParsedTagBlock {
    tag: string;
    value: string;
    raw: string;
    start: number;
    end: number;
}

export type TranscriptMessageKind =
    | 'plain'
    | 'claude-command'
    | 'claude-local-command-caveat'
    | 'claude-local-command-stdout'
    | 'tagged';

export interface TranscriptFormattedMessage {
    engine: 'claude-code' | 'generic' | 'plain';
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
}

const TAG_BLOCK_PATTERN = /<([a-z][a-z0-9-]*)>([\s\S]*?)<\/\1>/gi;

const TITLE_CASE_PATTERN = /[-_]+/g;

const normalizeTagValue = (value: string): string => value.replace(/\r/g, '').trim();

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

const parseClaudeCodeMessage = (content: string): TranscriptFormattedMessage | null => {
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

export const parseTranscriptMessage = (content: string): TranscriptFormattedMessage => {
    const claude = parseClaudeCodeMessage(content);
    if (claude) {
        return claude;
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
