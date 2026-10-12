/**
 * Declaration parser for guard rule R1 in `declare` mode (TypeScript port of `parse_declaration` in
 * hooks/shoal_guard.py; both replay tests/fixtures/declaration_cases.json).
 *
 * A declaration is a main-session shell call that is, after trimming, exactly
 * `: shoal-direct <reason>`.  `:` is the shell's no-op, so the call does nothing; the guard only reads
 * it.  The reason is double-quoted (a backslash escapes only `"`, `\`, `$` and the backtick; an
 * unescaped `$` or backtick would expand and is refused), single-quoted, or bare (plain words with no
 * shell syntax, expansion or globbing, no word starting with `=`).  It must be non-empty after
 * trimming.  Nothing may follow it and nothing may precede the `:`: no `;`, `&&`, `||`, `|`, newline,
 * subshell, redirection or comment.
 */

const PREFIX_RE = /^:[ \t]+shoal-direct[ \t]+/;
// Controls other than TAB: a declaration is one line of printable text.
const CONTROL_RE = /[\x00-\x08\x0a-\x1f\x7f-\x9f]/;
const CONTROL_ALL_RE = /[\x00-\x08\x0a-\x1f\x7f-\x9f]/g;
// A bare reason is plain words: no shell syntax, expansion or globbing (bash and zsh alike).
const BARE_BAD_RE = /[;&|<>()$`\\"'*?[\]{}~^!#]/;
export const MAX_REASON_CHARS = 200;

const trimBlank = (text: string, chars: string): string => {
  let start = 0;
  let end = text.length;
  while (start < end && chars.includes(text[start])) start += 1;
  while (end > start && chars.includes(text[end - 1])) end -= 1;
  return text.slice(start, end);
};

/** `rest` starts with `"`: the unescaped text when the string closes at the very end, else null. */
function doubleQuotedReason(rest: string): string | null {
  const buf: string[] = [];
  const n = rest.length;
  let i = 1;
  while (i < n) {
    const c = rest[i];
    if (c === "\\" && i + 1 < n && '"\\$`'.includes(rest[i + 1])) {
      buf.push(rest[i + 1]);
      i += 2;
    } else if (c === '"') {
      return i === n - 1 ? buf.join("") : null;
    } else if (c === "$" || c === "`") {
      return null;
    } else {
      buf.push(c);
      i += 1;
    }
  }
  return null;
}

/** The reason when `command` is exactly `: shoal-direct <reason>` (after trimming), else null. */
export function parseDeclaration(command: unknown): string | null {
  if (typeof command !== "string") return null;
  const text = trimBlank(command, " \t\r\n");
  if (CONTROL_RE.test(text)) return null;
  const head = PREFIX_RE.exec(text);
  if (head === null) return null;
  const rest = text.slice(head[0].length);
  if (rest === "") return null;
  let reason: string | null;
  if (rest[0] === "'") {
    const end = rest.indexOf("'", 1);
    reason = end === rest.length - 1 ? rest.slice(1, end) : null;
  } else if (rest[0] === '"') {
    reason = doubleQuotedReason(rest);
  } else if (BARE_BAD_RE.test(rest) || rest.split(/[ \t]+/).some((word) => word.startsWith("="))) {
    reason = null;
  } else {
    reason = rest;
  }
  if (reason === null) return null;
  reason = trimBlank(reason, " \t");
  return reason === "" ? null : reason;
}

/** The reason as logged: control characters removed, at most MAX_REASON_CHARS characters. */
export function logReason(reason: string): string {
  return Array.from(reason.replaceAll("\t", "").replace(CONTROL_ALL_RE, "")).slice(0, MAX_REASON_CHARS).join("");
}
