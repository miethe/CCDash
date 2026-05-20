"""Minimal UUID v7 generator (RFC 9562).

UUID v7 encodes a 48-bit unix millisecond timestamp in the most-significant
bits, making IDs monotonically increasing over time (within the granularity of
the system clock).  Same-millisecond calls use an incrementing 12-bit sequence
counter (rand_a) to guarantee within-process monotonicity.  Cross-process
monotonicity is NOT guaranteed and is not required by the daemon's event model.

Format (RFC 9562 §5.7):
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                           unix_ts_ms                          |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |          unix_ts_ms           |  ver  |       rand_a          |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |var|                        rand_b                             |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                            rand_b                             |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Bits:
    [0:48]   48-bit unix millisecond timestamp
    [48:52]  version nibble = 0x7
    [52:64]  12-bit seq counter (rand_a) — increments within the same ms tick
    [64:66]  variant bits = 0b10
    [66:128] 62 random bits (rand_b)

Within-process monotonicity:
    When two calls share the same millisecond timestamp, rand_a is a
    monotonically-increasing 12-bit counter seeded randomly at the first call
    for that tick.  When the counter wraps (>= 0x1000) or the timestamp
    advances, the counter resets to 0 and rand_b provides the randomness.
"""
from __future__ import annotations

import secrets
import time

# Module-level monotonic state (process-local; not thread-safe, but adequate
# since the daemon is async/single-threaded).
_last_ts_ms: int = 0
_seq: int = 0


def uuid7() -> str:
    """Generate a UUID v7 string (lowercase, hyphen-separated).

    Returns a RFC 9562 UUID v7 where the high 48 bits are the current unix
    timestamp in milliseconds.  Within a single millisecond tick, the 12-bit
    rand_a field acts as a monotonically-increasing sequence counter, ensuring
    within-process ordering.  The lower 62 bits (rand_b) remain cryptographically
    random.

    Returns:
        Lowercase UUID string, e.g. ``'018f2a3b-c4d5-7e6f-a1b2-c3d4e5f60718'``.
    """
    global _last_ts_ms, _seq  # noqa: PLW0603

    ts_ms = time.time_ns() // 1_000_000
    ts_ms &= 0xFFFF_FFFF_FFFF  # clamp to 48 bits

    if ts_ms == _last_ts_ms:
        _seq = (_seq + 1) & 0xFFF  # wrap at 12 bits
        rand_a = _seq
    else:
        _last_ts_ms = ts_ms
        _seq = 0
        rand_a = 0

    # 62 random bits for rand_b
    rand_b = int.from_bytes(secrets.token_bytes(8), "big") & 0x3FFF_FFFF_FFFF_FFFF

    # Assemble 128-bit integer
    uuid_int = (
        (ts_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )

    # Format as 8-4-4-4-12 hex string
    hex_str = f"{uuid_int:032x}"
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"
