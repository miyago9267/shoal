import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  createShoalRouteTool,
  SHOAL_REGISTRATION_KEY,
  ShoalOpenCodePlugin,
} from "../src/plugin/shoal-plugin.ts";

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
  shoalDir: string,
  provider: string,
  withRouting: boolean,
): Promise<void> {
  await mkdir(shoalDir, { recursive: true });
  await Bun.write(join(shoalDir, "catalog.json"), JSON.stringify(catalogFor(provider)));
  if (withRouting) {
    await Bun.write(join(shoalDir, "routing.json"), JSON.stringify(routingFor(provider)));
  }
}

async function runRoute(directory: string): Promise<{ title: string; output: string }> {
  const result = await createShoalRouteTool().execute(
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
    project = await mkdtemp(join(tmpdir(), "shoal-global-project-"));
    configDir = await mkdtemp(join(tmpdir(), "shoal-global-config-"));
    outside = await mkdtemp(join(tmpdir(), "shoal-global-outside-"));
    process.env.OPENCODE_CONFIG_DIR = configDir;
    Reflect.deleteProperty(globalThis, SHOAL_REGISTRATION_KEY);
  });

  afterEach(async () => {
    if (savedEnv.config === undefined) delete process.env.OPENCODE_CONFIG_DIR;
    else process.env.OPENCODE_CONFIG_DIR = savedEnv.config;
    if (savedEnv.home === undefined) delete process.env.HOME;
    else process.env.HOME = savedEnv.home;
    Reflect.deleteProperty(globalThis, SHOAL_REGISTRATION_KEY);
    for (const path of [project, configDir, outside]) {
      await rm(path, { recursive: true, force: true });
    }
  });

  test("project catalog wins over the global layer", async () => {
    await writeLayer(join(project, ".opencode", "shoal"), "projectprov", true);
    await writeLayer(join(configDir, "shoal"), "globalprov", true);

    const { output } = await runRoute(project);

    expect(output).toContain('"provider":"projectprov"');
    expect(output).not.toContain("globalprov");
  });

  test("falls back to the global layer when the project has no catalog", async () => {
    await writeLayer(join(configDir, "shoal"), "globalprov", true);

    const { output } = await runRoute(project);

    expect(output).toContain('"provider":"globalprov"');
  });

  test("global routing.json is optional and falls back to native routing", async () => {
    await writeLayer(join(configDir, "shoal"), "globalprov", false);

    const { output } = await runRoute(project);

    expect(output).toContain('"source":"agent_config"');
    expect(output).toContain('"provider":"globalprov"');
  });

  test("does not mix layers: project catalog without routing ignores the global routing", async () => {
    await writeLayer(join(project, ".opencode", "shoal"), "projectprov", false);
    await writeLayer(
      join(configDir, "shoal"),
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
    const home = await mkdtemp(join(tmpdir(), "shoal-global-home-"));
    try {
      delete process.env.OPENCODE_CONFIG_DIR;
      process.env.HOME = home;
      await writeLayer(join(home, ".config", "opencode", "shoal"), "homeprov", true);

      const { output } = await runRoute(project);

      expect(output).toContain('"provider":"homeprov"');
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  });

  test("rejects a shoal directory that is a symlink out of the config dir", async () => {
    await writeLayer(outside, "evilprov", true);
    await symlink(outside, join(configDir, "shoal"));

    const { title, output } = await runRoute(project);

    expect(title).toContain("invalid_config");
    expect(output).toContain("plugin.path");
    expect(output).not.toContain("evilprov");
  });

  test("rejects a routing.json symlink that escapes the config dir", async () => {
    await writeLayer(join(configDir, "shoal"), "globalprov", false);
    await Bun.write(join(outside, "routing.json"), JSON.stringify(routingFor("evilprov")));
    await symlink(join(outside, "routing.json"), join(configDir, "shoal", "routing.json"));

    const { title, output } = await runRoute(project);

    expect(title).toContain("invalid_config");
    expect(output).not.toContain("evilprov");
  });

  test("accepts a config dir that is itself a symlink", async () => {
    const real = join(outside, "real-config");
    await writeLayer(join(real, "shoal"), "linkedprov", true);
    const link = join(outside, "link-config");
    await symlink(real, link);
    process.env.OPENCODE_CONFIG_DIR = link;

    const { output } = await runRoute(project);

    expect(output).toContain('"provider":"linkedprov"');
  });
});

describe("duplicate plugin load", () => {
  beforeEach(() => {
    Reflect.deleteProperty(globalThis, SHOAL_REGISTRATION_KEY);
  });
  afterEach(() => {
    Reflect.deleteProperty(globalThis, SHOAL_REGISTRATION_KEY);
  });

  test("registers shoal_route only once for the same instance", async () => {
    const input = { directory: "/tmp/shoal-dedup-a" } as never;

    const first = await ShoalOpenCodePlugin(input);
    const second = await ShoalOpenCodePlugin(input);

    expect(first.tool?.shoal_route).toBeDefined();
    expect(second.tool).toBeUndefined();
    expect(Object.keys(second)).toEqual([]);
  });

  test("a different instance directory still gets its own tool", async () => {
    const a = await ShoalOpenCodePlugin({ directory: "/tmp/shoal-dedup-a" } as never);
    const b = await ShoalOpenCodePlugin({ directory: "/tmp/shoal-dedup-b" } as never);

    expect(a.tool?.shoal_route).toBeDefined();
    expect(b.tool?.shoal_route).toBeDefined();
  });
});
