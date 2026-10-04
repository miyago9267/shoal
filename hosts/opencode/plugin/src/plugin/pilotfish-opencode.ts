import { tool, type Plugin } from "@opencode-ai/plugin";
import { realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve } from "node:path";
import {
  resolveRoute,
  RouteResolutionError,
  type ResolvedOpenCodeCatalog,
  type RoleRoute,
  type RoutingConfig,
} from "../route-resolution.js";
import { serializeRouteReceipt } from "../receipt.js";
import { DEFAULT_ROLE_DEFINITIONS } from "../role-contract.js";

export type PilotfishPluginOptions = {
  catalogPath?: string;
  routingPath?: string;
};

const DEFAULT_CATALOG_PATH = ".opencode/pilotfish/catalog.json";
const DEFAULT_ROUTING_PATH = ".opencode/pilotfish/routing.json";
// 全域層固定放在 <config-dir>/pilotfish/，不受 catalogPath / routingPath 選項影響。
const GLOBAL_CATALOG_PATH = "pilotfish/catalog.json";
const GLOBAL_ROUTING_PATH = "pilotfish/routing.json";

// 同一個 OpenCode instance 可能同時載入全域與專案兩份 plugin（各自是獨立的 module），
// 所以用 Symbol.for 放在 globalThis，讓兩份 bundle 看到同一個登記表。
export const PILOTFISH_REGISTRATION_KEY = Symbol.for("shoal.pilotfish-opencode.route-registered");

function optionPath(
  options: PilotfishPluginOptions,
  key: keyof PilotfishPluginOptions,
  fallback: string,
): string {
  const value = options[key];
  if (value === undefined) return fallback;
  if (
    typeof value !== "string" ||
    value.trim().length === 0 ||
    value.includes("://")
  ) {
    throw new RouteResolutionError("invalid_config", { field: `plugin.${key}` });
  }
  return value;
}

function safeProjectPath(directory: string, configuredPath: string): string {
  const root = resolve(directory);
  const path = resolve(root, configuredPath);
  const relativePath = relative(root, path);
  if (
    isAbsolute(relativePath) ||
    relativePath === ".." ||
    relativePath.startsWith("../")
  ) {
    throw new RouteResolutionError("invalid_config", { field: "plugin.path" });
  }
  return path;
}

// 全域設定目錄：OPENCODE_CONFIG_DIR，未設定（或空字串）時為 ~/.config/opencode。
// 每次解析路由時才讀環境變數，測試與使用者都能在 process 內改指向。
function globalConfigDir(): string {
  const fromEnv = process.env.OPENCODE_CONFIG_DIR;
  return resolve(fromEnv !== undefined && fromEnv.trim().length > 0
    ? fromEnv
    : join(process.env.HOME || homedir(), ".config", "opencode"));
}

function isInside(root: string, path: string): boolean {
  const relativePath = relative(root, path);
  return !(
    isAbsolute(relativePath) ||
    relativePath === ".." ||
    relativePath.startsWith("../")
  );
}

// 全域層的穿越檢查：檔案存在時，realpath 必須落在 realpath(<config-dir>) 內，
// 防止 pilotfish/ 或檔案本身是指向 config dir 外部的 symlink。
async function globalLayerPath(configDir: string, relativePath: string): Promise<string> {
  const path = resolve(configDir, relativePath);
  if (!isInside(configDir, path)) {
    throw new RouteResolutionError("invalid_config", { field: "plugin.path" });
  }
  if (!(await Bun.file(path).exists())) return path;
  let realRoot: string;
  let realPath: string;
  try {
    realRoot = await realpath(configDir);
    realPath = await realpath(path);
  } catch {
    throw new RouteResolutionError("invalid_config", { field: "plugin.path" });
  }
  if (!isInside(realRoot, realPath)) {
    throw new RouteResolutionError("invalid_config", { field: "plugin.path" });
  }
  return path;
}

// R1：以 catalog.json 是否存在決定使用哪一層。專案層存在就只用專案層，
// 否則用全域層；同一層內 routing.json 維持 optional，不跨層混用。
async function resolveLayerPaths(
  directory: string,
  options: PilotfishPluginOptions,
): Promise<{ catalogPath: string; routingPath: string }> {
  const projectCatalog = safeProjectPath(
    directory,
    optionPath(options, "catalogPath", DEFAULT_CATALOG_PATH),
  );
  if (await Bun.file(projectCatalog).exists()) {
    return {
      catalogPath: projectCatalog,
      routingPath: safeProjectPath(
        directory,
        optionPath(options, "routingPath", DEFAULT_ROUTING_PATH),
      ),
    };
  }
  const configDir = globalConfigDir();
  const globalCatalog = await globalLayerPath(configDir, GLOBAL_CATALOG_PATH);
  if (!(await Bun.file(globalCatalog).exists())) {
    // 兩層都沒有 catalog：維持原本的專案層錯誤（catalog.missing）。
    return {
      catalogPath: projectCatalog,
      routingPath: projectCatalog,
    };
  }
  return {
    catalogPath: globalCatalog,
    routingPath: await globalLayerPath(configDir, GLOBAL_ROUTING_PATH),
  };
}

async function readJson<T>(path: string, label: string): Promise<T> {
  const file = Bun.file(path);
  if (!(await file.exists())) {
    throw new RouteResolutionError("invalid_config", { field: `${label}.missing` });
  }
  try {
    return (await file.json()) as T;
  } catch {
    throw new RouteResolutionError("invalid_config", { field: `${label}.json` });
  }
}

async function readOptionalJson<T>(path: string, label: string): Promise<T | undefined> {
  const file = Bun.file(path);
  if (!(await file.exists())) return undefined;
  try {
    return (await file.json()) as T;
  } catch {
    throw new RouteResolutionError("invalid_config", { field: `${label}.json` });
  }
}

function nativeRouting(): RoutingConfig {
  const roles: Record<string, RoleRoute> = {};
  for (const role of DEFAULT_ROLE_DEFINITIONS) {
    roles[role.id] = { agent: role.id, fallback: "none" };
  }
  return { version: 1, roles };
}

function pluginOptions(value: Record<string, unknown> | undefined): PilotfishPluginOptions {
  return {
    catalogPath: typeof value?.catalogPath === "string" ? value.catalogPath : undefined,
    routingPath: typeof value?.routingPath === "string" ? value.routingPath : undefined,
  };
}

export function createPilotfishRouteTool(options: PilotfishPluginOptions = {}) {
  return tool({
    description:
      "Validate one customer-owned Pilotfish role route for an OpenCode role invocation. This reports a route receipt; it does not change the current session model.",
    args: {
      role: tool.schema.string().describe("Pilotfish role or customer alias"),
      provider: tool.schema.string().optional().describe("Explicit provider override"),
      model: tool.schema.string().optional().describe("Explicit model override"),
      variant: tool.schema.string().optional().describe("Explicit model variant"),
      requiredCapabilities: tool.schema
        .array(tool.schema.string())
        .optional()
        .describe("Capabilities required by this role invocation"),
      parentProvider: tool.schema.string().optional(),
      parentModel: tool.schema.string().optional(),
      parentVariant: tool.schema.string().optional(),
    },
    async execute(args, context) {
      const hasExplicit =
        args.provider !== undefined ||
        args.model !== undefined ||
        args.variant !== undefined;
      if (hasExplicit && (args.provider === undefined || args.model === undefined)) {
        throw new RouteResolutionError("invalid_config", {
          field: "explicit.provider_and_model",
        });
      }

      const hasParent =
        args.parentProvider !== undefined ||
        args.parentModel !== undefined ||
        args.parentVariant !== undefined;
      if (hasParent && (args.parentProvider === undefined || args.parentModel === undefined)) {
        throw new RouteResolutionError("invalid_config", {
          field: "parentModel.provider_and_model",
        });
      }

      try {
        const layer = await resolveLayerPaths(context.directory, options);
        const catalog = await readJson<ResolvedOpenCodeCatalog>(layer.catalogPath, "catalog");
        const config =
          (await readOptionalJson<RoutingConfig>(layer.routingPath, "routing")) ??
          nativeRouting();
        const result = resolveRoute({
          role: args.role,
          config,
          catalog,
          explicit:
            args.provider === undefined || args.model === undefined
              ? undefined
              : {
                  provider: args.provider,
                  model: args.model,
                  ...(args.variant === undefined ? {} : { variant: args.variant }),
                },
          parentModel:
            args.parentProvider === undefined || args.parentModel === undefined
              ? undefined
              : {
                  provider: args.parentProvider,
                  model: args.parentModel,
                  ...(args.parentVariant === undefined
                    ? {}
                    : { variant: args.parentVariant }),
                },
          requiredCapabilities: args.requiredCapabilities,
        });
        context.metadata({
          title: `Pilotfish route: ${result.receipt.role}`,
          metadata: { receipt: result.receipt, attempts: result.attempts },
        });
        return {
          title: `Pilotfish route: ${result.receipt.resolved.provider}/${result.receipt.resolved.model}`,
          output: serializeRouteReceipt(result.receipt),
          metadata: { receipt: result.receipt, attempts: result.attempts },
        };
      } catch (error) {
        if (error instanceof RouteResolutionError) {
          return {
            title: `Pilotfish route rejected: ${error.code}`,
            output: JSON.stringify({ code: error.code, details: error.details }),
            metadata: { code: error.code, details: error.details },
          };
        }
        throw error;
      }
    },
  });
}

// R2a：同一個 instance（以 input.directory 區分）只註冊一次 pilotfish_route。
// 用 directory 當 key 而不是整個 process 一個旗標，是因為 OpenCode 的 plugin 以
// instance（目錄）為單位初始化；同一個 server 開多個專案目錄時，每個目錄都要有這個 tool。
export const PilotfishOpenCodePlugin: Plugin = async (input, options) => {
  const slot = globalThis as unknown as Record<symbol, Set<string> | undefined>;
  const registered = (slot[PILOTFISH_REGISTRATION_KEY] ??= new Set<string>());
  const key = resolve(input?.directory ?? "");
  if (registered.has(key)) return {};
  registered.add(key);
  return {
    tool: {
      pilotfish_route: createPilotfishRouteTool(pluginOptions(options)),
    },
  };
};

export default PilotfishOpenCodePlugin;
