/**
 * Shell-write detector for guard rule G5 (TypeScript port of `shell_write_targets` in
 * hooks/shoal_guard.py; both replay tests/fixtures/shell_write_cases.json).
 *
 * A literal reading of a shell command string, not a shell parser.  Counts `>`, `>>`, `>|`, `&>`
 * redirects to a word, `tee [-a] file...`, `sed -i` / `--in-place` and `perl -i` (`-pi`, `-0pi`, `-i.bak`), each at command position
 * (after `;`, `|`, `&&`, newline, `(`, `then`, `do`, or wrappers such as `sudo`, `env`, `xargs`,
 * `find -exec`).  Never counts: `>&2` / `2>&1` duplications, `<` input, here-document bodies,
 * quoted text, `[[ ]]`, `(( ))`, `$(( ))`, comments and `>(...)`.  Writes through any other interpreter or
 * command (node, `perl -e` code that opens a file, cp, mv, patch, git apply, dd, ...) are not detected.
 *
 * Python (`python[0-9.]*` at command position): when one runs, the whole command text is scanned with
 * PY_WRITE_RE (literal-mode `open(..., 'w|a|x')`, `.write_text(` / `.write_bytes(`, `shutil.copy*(` /
 * `shutil.move(`, `os.remove|unlink|rename|replace(`); `open('literal', ...)` reports that path, any other
 * hit UNKNOWN_TARGET, after the shell targets.  A guardrail, not a sandbox: exec/eval, getattr,
 * subprocess, script files, computed modes, `node -e`, cp and mv are not covered.
 */

/** Target reported when a write is certain but its file is not (see the Python module). */
export const UNKNOWN_TARGET = "$?";

const WORD_BREAK = " \t\r\n;|&<>()";
const ASSIGNMENT_RE = /^[A-Za-z_][A-Za-z0-9_]*=/;
const DOUBLE_BRACKET_END_RE = /(?:^|\s)\]\](?=$|[\s;&|)])/g;
const COMMAND_KEEP = new Set(["then", "do", "else", "elif", "if", "while", "until", "!", "{"]);
const COMMAND_WRAPPERS = new Set(["sudo", "command", "exec", "env", "time", "nohup", "builtin", "xargs"]);
const FIND_EXEC = new Set(["-exec", "-execdir"]);
const PYTHON_NAME_RE = /^python[0-9.]*$/;
const PY_WRITE_RE = new RegExp(
  String.raw`\bopen\(\s*(?:(['"])([^'"\n]*)\1)?[^\n]{0,200}?,\s*(?:mode=)?['"][rbt]*[wax][rbt+]*['"]` +
    String.raw`|\.write_(?:text|bytes)\(` +
    String.raw`|\bshutil\.(?:copy\w*|move)\(` +
    String.raw`|\bos\.(?:remove|unlink|rename|replace)\(`,
  "g",
);

const isDigit = (c: string): boolean => c >= "0" && c <= "9";

/** `text[start]` is `(`: index just after the matching `)` (text.length when unbalanced). */
function skipParens(text: string, start: number): number {
  let depth = 0;
  let i = start;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (c === "\\") {
      i += 2;
      continue;
    }
    if (c === "'") {
      const j = text.indexOf("'", i + 1);
      i = j < 0 ? n : j + 1;
      continue;
    }
    if (c === '"') {
      i += 1;
      while (i < n && text[i] !== '"') i += text[i] === "\\" ? 2 : 1;
      i += 1;
      continue;
    }
    if (c === "(") depth += 1;
    else if (c === ")") {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
    i += 1;
  }
  return n;
}

/** One shell word from `start`: quotes removed, `$(...)` / `${...}` / backticks kept raw. */
function readWord(text: string, start: number): [string, number] {
  const buf: string[] = [];
  let i = start;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    const next = i + 1 < n ? text[i + 1] : "";
    if (WORD_BREAK.includes(c)) break;
    if (c === "\\") {
      if (next !== "" && next !== "\n") buf.push(next);
      i += 2;
    } else if (c === "'") {
      let j = text.indexOf("'", i + 1);
      if (j < 0) j = n;
      buf.push(text.slice(i + 1, j));
      i = j + 1;
    } else if (c === '"') {
      let j = i + 1;
      while (j < n && text[j] !== '"') j += text[j] === "\\" ? 2 : 1;
      buf.push(text.slice(i + 1, Math.min(j, n)));
      i = j + 1;
    } else if (c === "$" && next === "(") {
      const j = skipParens(text, i + 1);
      buf.push(text.slice(i, j));
      i = j;
    } else if (c === "$" && next === "{") {
      const j = text.indexOf("}", i + 2);
      const end = j < 0 ? n : j + 1;
      buf.push(text.slice(i, end));
      i = end;
    } else if (c === "$" && next === "'") {
      let j = i + 2;
      while (j < n && text[j] !== "'") j += text[j] === "\\" ? 2 : 1;
      buf.push(text.slice(i + 2, Math.min(j, n)));
      i = j + 1;
    } else if (c === "`") {
      const j = text.indexOf("`", i + 1);
      const end = j < 0 ? n : j + 1;
      buf.push(text.slice(i, end));
      i = end;
    } else {
      buf.push(c);
      i += 1;
    }
  }
  return [buf.join(""), Math.min(i, n)];
}

function teeFiles(args: string[]): string[] {
  return args.filter((a) => a !== "" && !a.startsWith("-"));
}

/** File operands of a `sed -i` / `--in-place` call; [] when the call does not edit in place. */
function sedInPlaceFiles(args: string[]): string[] {
  let inPlace = false;
  let haveScript = false;
  const positional: string[] = [];
  let k = 0;
  while (k < args.length) {
    const a = args[k];
    if (a === "--") {
      positional.push(...args.slice(k + 1));
      break;
    }
    if (a.startsWith("--")) {
      if (a === "--in-place" || a.startsWith("--in-place=")) inPlace = true;
      else if (a === "--expression" || a === "--file") {
        haveScript = true;
        k += 1;
      } else if (a.startsWith("--expression=") || a.startsWith("--file=")) haveScript = true;
    } else if (a.startsWith("-") && a.length > 1) {
      const cluster = a.slice(1);
      for (let index = 0; index < cluster.length; index += 1) {
        const letter = cluster[index];
        if (letter === "i") {
          inPlace = true;
          break;
        }
        if (letter === "e" || letter === "f" || letter === "l") {
          haveScript = haveScript || letter !== "l";
          if (index === cluster.length - 1) k += 1; // the value is the next argument
          break;
        }
      }
    } else if (a !== "") {
      positional.push(a); // an empty word is macOS's `-i ''` suffix, never a file or the script
    }
    k += 1;
  }
  if (!inPlace) return [];
  const files = haveScript ? positional : positional.slice(1);
  return files.length > 0 ? files : [UNKNOWN_TARGET];
}

/** `text[i]` starts a digit run directly followed by `<` or `>` (a file-descriptor number). */
function fdPrefix(text: string, start: number): boolean {
  let i = start;
  while (i < text.length && isDigit(text[i])) i += 1;
  return i < text.length && (text[i] === "<" || text[i] === ">");
}

/** File operands of a `perl -i` call (`-pi`, `-0pi`, `-i.bak`, `--in-place`); [] when it does not edit in place. */
function perlInPlaceFiles(args: string[]): string[] {
  let inPlace = false;
  let haveScript = false;
  const positional: string[] = [];
  let k = 0;
  while (k < args.length) {
    const a = args[k];
    if (a === "--") {
      positional.push(...args.slice(k + 1));
      break;
    }
    if (a.startsWith("--")) {
      inPlace = inPlace || a === "--in-place" || a.startsWith("--in-place=");
    } else if (a.startsWith("-") && a.length > 1) {
      const cluster = a.slice(1);
      for (let index = 0; index < cluster.length; index += 1) {
        const letter = cluster[index];
        if (letter === "i") {
          inPlace = true;
          break;
        }
        if (letter === "e" || letter === "E") {
          haveScript = true;
          if (index === cluster.length - 1) k += 1; // the script is the next argument
          break;
        }
        if ("IMmFxdDVC".includes(letter)) break; // the rest of the word (or the next argument) is its value
      }
    } else if (a !== "") {
      positional.push(a);
    }
    k += 1;
  }
  if (!inPlace) return [];
  const files = haveScript ? positional : positional.slice(1);
  return files.length > 0 ? files : [UNKNOWN_TARGET];
}

/** File targets that `command` writes by a literal reading of its text (G5). */
export function shellWriteTargets(command: string): string[] {
  if (
    !command.includes(">") &&
    !command.includes("tee") &&
    !command.includes("sed") &&
    !command.includes("perl") &&
    !command.includes("python")
  ) {
    return [];
  }
  const targets: string[] = [];
  const n = command.length;
  let i = 0;
  let cmdPos = true;
  let wrapped = false;
  let name: string | null = null;
  let args: string[] = [];
  let heredocs: Array<[string, boolean]> = [];
  let pythonRan = false;

  const flush = (): void => {
    if (name !== null && PYTHON_NAME_RE.test(name)) pythonRan = true;
    else if (name === "tee") targets.push(...teeFiles(args));
    else if (name === "sed") targets.push(...sedInPlaceFiles(args));
    else if (name === "perl") targets.push(...perlInPlaceFiles(args));
    name = null;
    args = [];
    cmdPos = true;
    wrapped = false;
  };
  const skipBlanks = (): void => {
    while (i < n && (command[i] === " " || command[i] === "\t")) i += 1;
  };

  while (i < n) {
    const c = command[i];
    const next = i + 1 < n ? command[i + 1] : "";
    if (c === " " || c === "\t" || c === "\r") {
      i += 1;
    } else if (c === "\n") {
      flush();
      i += 1;
      for (const [delim, strip] of heredocs) {
        // bodies start on the next line
        while (i < n) {
          let end = command.indexOf("\n", i);
          if (end < 0) end = n;
          const line = command.slice(i, end);
          i = Math.min(end + 1, n);
          if ((strip ? line.replace(/^\t+/, "") : line) === delim) break;
        }
      }
      heredocs = [];
    } else if (c === "#" && (i === 0 || " \t\n;|&()".includes(command[i - 1]))) {
      const end = command.indexOf("\n", i);
      i = end < 0 ? n : end;
    } else if (c === ";" || c === "|" || (c === "&" && next !== ">")) {
      flush();
      i += 1;
      if (i < n && ";|&".includes(command[i])) i += 1;
    } else if (c === ">" || c === "&") {
      // `&>` writes both streams to a file
      i += c === "&" ? 2 : 1;
      if (i < n && (command[i] === ">" || command[i] === "|")) i += 1;
      else if (i < n && command[i] === "(") continue; // process substitution `>(cmd)`
      const dup = c === ">" && i < n && command[i] === "&";
      if (dup) i += 1;
      skipBlanks();
      let word: string;
      [word, i] = readWord(command, i);
      const fdOnly = dup && (word === "" || word === "-" || /^[0-9]+$/.test(word) || word.startsWith("$"));
      if (word !== "" && !fdOnly) targets.push(word);
    } else if (c === "<") {
      if (command.startsWith("<<<", i)) {
        i += 3;
        skipBlanks();
        [, i] = readWord(command, i);
      } else if (next === "<") {
        i += 2;
        const strip = i < n && command[i] === "-";
        if (strip) i += 1;
        skipBlanks();
        let delim: string;
        [delim, i] = readWord(command, i);
        heredocs.push([delim, strip]);
      } else if (next === "(") {
        i += 1; // process substitution `<(cmd)`
      } else {
        i += 1;
        if (i < n && (command[i] === "&" || command[i] === ">")) i += 1;
        skipBlanks();
        [, i] = readWord(command, i);
      }
    } else if (c === "(") {
      if (next === "(") {
        i = skipParens(command, i); // `(( ... ))`
        flush();
        cmdPos = false;
      } else {
        flush();
        i += 1;
      }
    } else if (c === ")") {
      flush();
      i += 1;
    } else if (isDigit(c) && fdPrefix(command, i)) {
      while (isDigit(command[i])) i += 1;
    } else {
      let word: string;
      [word, i] = readWord(command, i);
      if (FIND_EXEC.has(word) && !cmdPos) {
        flush();
        wrapped = true;
      } else if (word === "[[" && cmdPos) {
        DOUBLE_BRACKET_END_RE.lastIndex = i;
        const found = DOUBLE_BRACKET_END_RE.exec(command);
        i = found ? found.index + found[0].length : n;
        cmdPos = false;
      } else if (!cmdPos) {
        args.push(word);
      } else if (ASSIGNMENT_RE.test(word) || COMMAND_KEEP.has(word)) {
        // still at command position
      } else if (wrapped && word.startsWith("-")) {
        // an option of the wrapper
      } else if (COMMAND_WRAPPERS.has(word)) {
        wrapped = true;
      } else {
        name = word.slice(word.lastIndexOf("/") + 1);
        args = [];
        cmdPos = false;
        wrapped = false;
      }
    }
  }
  flush();
  if (pythonRan) {
    for (const match of command.matchAll(PY_WRITE_RE)) targets.push(match[2] || UNKNOWN_TARGET);
  }
  return targets;
}
