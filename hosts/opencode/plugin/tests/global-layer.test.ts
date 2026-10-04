import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  createPilotfishRouteTool,
  PILOTFISH_REGISTRATION_KEY,
  PilotfishOpenCodePlugin,
} from "../src/plugin/pilotfish-opencode.ts";

// 全域設定層（R1）與重複載入去重（R2a）。
// 全域目錄一律由 OPENCODE_CONFIG_DIR（或 HOME）指到 temp，不碰真實的 ~/.config/opencode。

function catalogFor(provider: string) {
  return {
    agents: {
      scout: { mode: "subagent", available: true, model: { provider, model: "scout" } },
    },
    providers: {
      [provider]: {
        authenticated: true,
        identity: provider,
        models: { scout: { capabilities: { supported: ["tools"], source: "catalog" } } },
      },
    },
  };
}

function routingFor(provider: string) {
  return {
    version: 1,
    roles: {
      scout: {
        agent: "scout",
        candidates: [{ provider, model: "scout" }],
        fallback: "none",
      },
    },
  };
}

async function writeLayer(
  pilotfishDir: string,
  provider: string,
  withRouting: boolean,
): Promise<void> {
  await mkdir(pilotfishDir, { recursive: true });
  await Bun.write(join(pilotfishDir, "catalog.json"), JSON.stringify(catalogFor(provider)));
  if (withRouting) {
    await Bun.write(join(pilotfishDir, "routing.json"), JSON.stringify(routingFor(provider)));
  }
}

async function runRoute(directory: string): Promise<{ title: string; output: string }> {
  const result = await createPilotfishRouteTool().execute(
    { role: "scout" },
    {
      worktree: directory,
      directory,
      sessionID: "test",
      messageID: "test",
      agent: "scout",
      abort: new AbortController().signal,
      metadata: () => undefined,
      ask: async () => undefined,
    },
  );
  if (typeof result === "string") throw new Error("expected structured tool result");
  return { title: result.title ?? "", output: result.output };
}

describe("global config layer", () => {
  let project: string;
  let configDir: string;
  let outside: string;
  const savedEnv = { config: process.env.OPENCODE_CONFIG_DIR, home: process.env.HOME };

  beforeEach(async () => {
    project = await mkdtemp(join(tmpdir(), "pilotfish-global-project-"));
    configDir = await mkdtemp(join(tmpdir(), "pilotfish-global-config-"));
    outside = await mkdtemp(join(tmpdir(), "pilotfish-global-outside-"));
    process.env.OPENCODE_CONFIG_DIR = configDir;
    Reflect.deleteProperty(globalThis, PILOTFISH_REGISTRATION_KEY);
  });

  afterEach(async () => {
    if (savedEnv.config === undefined) delete process.env.OPENCODE_CONFIG_DIR;
    else process.env.OPENCODE_CONFIG_DIR = savedEnv.config;
    if (savedEnv.home === undefined) delete process.env.HOME;
    else process.env.HOME = savedEnv.home;
    Reflect.deleteProperty(globalThis, PILOTFISH_REGISTRATION_KEY);
    for (const path of [project, configDir, outside]) {
      await rm(path, { recursive: true, force: true });
    }
  });

  test("project catalog wins over the global layer", async () => {
    await writeLayer(join(project, ".opencode", "pilotfish"), "projectprov", true);
    await writeLayer(join(configDir, "pilotfish"), "globalprov", true);

    const { output } = await runRoute(project);

    expect(output).toContain('"provider":"projectprov"');
    expect(output).not.toContain("globalprov");
  });

  test("falls back to the global layer when the project has no catalog", async () => {
    await writeLayer(join(configDir, "pilotfish"), "globalprov", true);

    const { output } = await runRoute(project);

    expect(output).toContain('"provider":"globalprov"');
  });

  test("global routing.json is optional and falls back to native routing", async () => {
    await writeLayer(join(configDir, "pilotfish"), "globalprov", false);

    const { output } = await runRoute(project);

    expect(output).toContain('"source":"agent_config"');
    expect(output).toContain('"provider":"globalprov"');
  });

  test("does not mix layers: project catalog without routing ignores the global routing", async () => {
    await writeLayer(join(project, ".opencode", "pilotfish"), "projectprov", false);
    await writeLayer(
      join(configDir, "pilotfish"),
      "globalprov",
      true,
    );

    const { output } = await runRoute(project);

    expect(output).toContain('"source":"agent_config"');
    expect(output).toContain('"provider":"projectprov"');
    expect(output).not.toContain("globalprov");
  });

  test("reports catalog.missing when neither layer has a catalog", async () => {
    const { title, output } = await runRoute(project);

    expect(title).toContain("invalid_config");
    expect(output).toContain("catalog.missing");
  });

  test("uses ~/.config/opencode when OPENCODE_CONFIG_DIR is unset", async () => {
    const home = await mkdtemp(join(tmpdir(), "pilotfish-global-home-"));
    try {
      delete process.env.OPENCODE_CONFIG_DIR;
      process.env.HOME = home;
      await writeLayer(join(home, ".config", "opencode", "pilotfish"), "homeprov", true);

      const { output } = await runRoute(project);

      expect(output).toContain('"provider":"homeprov"');
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  });

  test("rejects a pilotfish directory that is a symlink out of the config dir", async () => {
    await writeLayer(outside, "evilprov", true);
    await symlink(outside, join(configDir, "pilotfish"));

    const { title, output } = await runRoute(project);

    expect(title).toContain("invalid_config");
    expect(output).toContain("plugin.path");
    expect(output).not.toContain("evilprov");
  });

  test("rejects a routing.json symlink that escapes the config dir", async () => {
    await writeLayer(join(configDir, "pilotfish"), "globalprov", false);
    await Bun.write(join(outside, "routing.json"), JSON.stringify(routingFor("evilprov")));
    await symlink(join(outside, "routing.json"), join(configDir, "pilotfish", "routing.json"));

    const { title, output } = await runRoute(project);

    expect(title).toContain("invalid_config");
    expect(output).not.toContain("evilprov");
  });

  test("accepts a config dir that is itself a symlink", async () => {
    const real = join(outside, "real-config");
    await writeLayer(join(real, "pilotfish"), "linkedprov", true);
    const link = join(outside, "link-config");
    await symlink(real, link);
    process.env.OPENCODE_CONFIG_DIR = link;

    const { output } = await runRoute(project);

    expect(output).toContain('"provider":"linkedprov"');
  });
});

describe("duplicate plugin load", () => {
  beforeEach(() => {
    Reflect.deleteProperty(globalThis, PILOTFISH_REGISTRATION_KEY);
  });
  afterEach(() => {
    Reflect.deleteProperty(globalThis, PILOTFISH_REGISTRATION_KEY);
  });

  test("registers pilotfish_route only once for the same instance", async () => {
    const input = { directory: "/tmp/pilotfish-dedup-a" } as never;

    const first = await PilotfishOpenCodePlugin(input);
    const second = await PilotfishOpenCodePlugin(input);

    expect(first.tool?.pilotfish_route).toBeDefined();
    expect(second.tool).toBeUndefined();
    expect(Object.keys(second)).toEqual([]);
  });

  test("a different instance directory still gets its own tool", async () => {
    const a = await PilotfishOpenCodePlugin({ directory: "/tmp/pilotfish-dedup-a" } as never);
    const b = await PilotfishOpenCodePlugin({ directory: "/tmp/pilotfish-dedup-b" } as never);

    expect(a.tool?.pilotfish_route).toBeDefined();
    expect(b.tool?.pilotfish_route).toBeDefined();
  });
});
