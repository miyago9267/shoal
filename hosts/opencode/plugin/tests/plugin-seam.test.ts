import { beforeEach, describe, expect, test } from "bun:test";
import { mkdir, rm } from "node:fs/promises";
import { join } from "node:path";
import {
  createShoalRouteTool,
  SHOAL_REGISTRATION_KEY,
  ShoalOpenCodePlugin,
} from "../src/plugin/shoal-plugin.ts";

const catalog = {
  agents: { scout: { mode: "subagent", available: true } },
  providers: {
    direct: {
      authenticated: true,
      identity: "direct",
      models: {
        scout: {
          capabilities: { supported: ["tools"], source: "catalog" },
        },
      },
    },
  },
};

const routing = {
  version: 1,
  roles: {
    scout: {
      agent: "scout",
      candidates: [{ provider: "direct", model: "scout" }],
      fallback: "none",
    },
  },
};

describe("OpenCode plugin seam", () => {
  // 去重登記表在整個 bun test process 共用；每個 test 前清掉，避免互相影響。
  beforeEach(() => {
    Reflect.deleteProperty(globalThis, SHOAL_REGISTRATION_KEY);
  });

  test("exposes the route tool and the guard hooks, and does not mutate model hooks", async () => {
    const hooks = await ShoalOpenCodePlugin({} as never);

    expect(Object.keys(hooks).sort()).toEqual(["chat.message", "tool", "tool.execute.before"]);
    expect(hooks.tool?.shoal_route).toBeDefined();
  });

  test("reads customer-owned files and returns a redacted receipt", async () => {
    const directory = join("/tmp", `shoal-opencode-${crypto.randomUUID()}`);
    await mkdir(join(directory, ".opencode", "shoal"), { recursive: true });
    await Bun.write(
      join(directory, ".opencode", "shoal", "catalog.json"),
      JSON.stringify(catalog),
    );
    await Bun.write(
      join(directory, ".opencode", "shoal", "routing.json"),
      JSON.stringify(routing),
    );

    try {
      const routeTool = createShoalRouteTool();
      const result = await routeTool.execute(
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

      expect(typeof result).toBe("object");
      if (typeof result !== "string") {
        expect(result.output).toContain('"provider":"direct"');
        expect(result.output).not.toContain("api_key");
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  test("uses native agent model metadata when the optional overlay is absent", async () => {
    const directory = join("/tmp", `shoal-opencode-native-${crypto.randomUUID()}`);
    await mkdir(join(directory, ".opencode", "shoal"), { recursive: true });
    await Bun.write(
      join(directory, ".opencode", "shoal", "catalog.json"),
      JSON.stringify({
        ...catalog,
        agents: {
          scout: {
            mode: "subagent",
            available: true,
            model: { provider: "direct", model: "scout" },
          },
        },
      }),
    );

    try {
      const routeTool = createShoalRouteTool();
      const result = await routeTool.execute(
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

      expect(typeof result).toBe("object");
      if (typeof result !== "string") {
        expect(result.output).toContain('"source":"agent_config"');
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});
