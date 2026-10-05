// OpenCode 把入口 module 的每個 export 都當成 plugin function 載入，非 function 的 export
// 會讓整個 plugin 載入失敗（"Plugin export is not a function"）。所以建置入口只 re-export
// plugin 本體；helper（registration key、route tool 工廠）留在 ./pilotfish-plugin.ts。
import { PilotfishOpenCodePlugin } from "./pilotfish-plugin.js";

export default PilotfishOpenCodePlugin;
