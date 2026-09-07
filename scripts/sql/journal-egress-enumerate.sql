-- VENDORED from agentic_meta_dev/scripts/ccdash-journal-egress-enumerate.sql (2026-09-07).
-- Runner: scripts/journal_egress_enumerate.py  (read-only; counts only; deletes nothing).
-- Baseline measured before CCDash adopted the predicate: 208 rows / 59 sessions.
--
-- READ-ONLY enumeration v2. COUNTS ONLY — no row content selected or printed.
--
-- v1 measured `content` alone and returned 10. That was the WRONG INSTRUMENT:
-- session_messages.content averages 11 chars on Bash tool rows (421,313 of them,
-- ZERO containing a recognizable shell command), while metadata_json averages
-- 3,979 chars and carries the tool input on 349,609 of them. So v1's `journal_command`
-- count of 4 was prose mentioning the verb, not the tool calls themselves.
-- Haystack here is content || metadata_json.
--
-- Removal is Mode-D: Nick's decision, never the enumerating leg's.
-- node_01M1YQE73ZT7T4EZSKNYX007ER, 2026-09-07.

\pset pager off

WITH hay AS (
    SELECT
        m.id,
        m.session_id,
        m.tool_call_id,
        m.related_tool_call_id,
        m.project_id,
        s.cwd,
        coalesce(m.content, '') || ' ' || coalesce(m.metadata_json, '') AS blob
    FROM session_messages m
    LEFT JOIN sessions s
           ON s.project_id = m.project_id AND s.id = m.session_id
),
tainted AS (
    SELECT DISTINCT project_id, tool_call_id
    FROM hay
    WHERE tool_call_id IS NOT NULL
      AND tool_call_id <> ''
      AND blob ~ 'op[[:space:]]+journal[[:space:]]+(write|read|surface)([[:space:]]|\\|"|$)'
),
flagged AS (
    SELECT
        h.id,
        h.session_id,
        CASE
            -- Precedence mirrors TranscriptFilter.should_exclude exactly.
            WHEN h.cwd ~ '(^|/)\.metis(/|$)'                        THEN 'metis_cwd'
            WHEN h.blob ~ 'op[[:space:]]+journal[[:space:]]+(write|read|surface)([[:space:]]|\\|"|$)'
                                                                    THEN 'journal_command'
            WHEN t.tool_call_id IS NOT NULL                         THEN 'journal_command_result'
            WHEN h.blob LIKE '%JOURNAL ENTRY START%'                THEN 'journal_marker'
            WHEN h.blob ~ 'jrn_[0-9]{8}_[0-9a-f]{8}'                THEN 'journal_entry_id'
            ELSE NULL
        END AS reason
    FROM hay h
    LEFT JOIN tainted t
           ON t.project_id = h.project_id
          AND t.tool_call_id = COALESCE(NULLIF(h.related_tool_call_id, ''), '~none~')
)
SELECT
    COALESCE(reason, 'TOTAL_MATCHED')  AS reason,
    count(*)                           AS matched_rows,
    count(DISTINCT session_id)         AS distinct_sessions
FROM flagged
WHERE reason IS NOT NULL
GROUP BY ROLLUP (reason)
ORDER BY 1;
