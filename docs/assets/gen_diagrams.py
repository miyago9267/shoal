"""產生 shoal 的 overview / routing / orchestration / guard 四張圖，各有 zh-TW、en、zh-CN 共 12 個 SVG。
在 repo 根目錄執行 `python3 docs/assets/gen_diagrams.py`，輸出到 docs/assets/（可用第一個參數改目錄）。
此副本已用 patina 審閱過。
"""
import sys, re
from xml.sax.saxutils import escape
OUT = sys.argv[1] if len(sys.argv) > 1 else 'docs/assets'
W = 960
FONTS = {
 'zh-TW': '-apple-system, BlinkMacSystemFont, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, sans-serif',
 'zh-CN': '-apple-system, BlinkMacSystemFont, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
 'en': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", system-ui, sans-serif',
}
CSS = """
.bg{fill:#f7f9fc}.fg{fill:#152238}.muted{fill:#5b6b80}.ln{stroke:#c9d4e2;fill:none;stroke-width:1.5}
.card{fill:#fff;stroke:#c9d4e2;stroke-width:1.2}
.sb{fill:#eaf0ff;stroke:#a9bff5}.sg{fill:#e3f5ec;stroke:#a6dcc0}.sa{fill:#fff1dc;stroke:#ecc98d}.sp{fill:#efe9ff;stroke:#c9b8f1}.sr{fill:#fde8e8;stroke:#eeb0b0}.sx{fill:#eef1f5;stroke:#b4bfcd;stroke-dasharray:5 4}
.ar{stroke:#5b6b80;stroke-width:1.8;fill:none}.arh{fill:#5b6b80}
.t{font-weight:700;font-size:26px}.st{font-size:15px}.h{font-weight:700;font-size:16px}.b{font-size:15px}.sm{font-size:13px}.xs{font-size:12px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.bold{font-weight:700}
@media (prefers-color-scheme: dark){
.bg{fill:#101827}.fg{fill:#f3f6fb}.muted{fill:#a9b6c8}.ln{stroke:#3a4a60}
.card{fill:#172235;stroke:#3a4a60}
.sb{fill:#1b2d59;stroke:#4f74c4}.sg{fill:#173d2e;stroke:#3f9470}.sa{fill:#473219;stroke:#a07a43}.sp{fill:#2d2247;stroke:#7059a8}.sr{fill:#4a2323;stroke:#a35a5a}.sx{fill:#1d2838;stroke:#5d6d82}
.ar{stroke:#a9b6c8}.arh{fill:#a9b6c8}}
"""
def wid(s, size, mono=False):
    w = 0
    for c in s:
        if ord(c) > 0x2E80: w += 1.0
        elif mono: w += 0.6
        else: w += 0.58
    return w * size
class S:
    def __init__(s, lang, h, title, desc):
        s.lang, s.h, s.o = lang, h, []
        s.title, s.desc = title, desc
    def add(s, x): s.o.append(x)
    def rect(s, x, y, w, h, cls, r=10):
        s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" class="{cls}"/>')
    def text(s, x, y, txt, cls='b fg', anchor='start', maxw=None):
        size = 12 if ' xs ' in f' {cls} ' else 26 if ' t ' in f' {cls} ' else 16 if ' h ' in f' {cls} ' else 13 if ' sm ' in f' {cls} ' else 15
        mono = 'mono' in cls
        w = wid(txt, size, mono)
        if maxw is not None and w > maxw:
            raise SystemExit(f'OVERFLOW {s.lang}: "{txt}" {w:.0f}>{maxw}')
        s.add(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(txt)}</text>')
    def box(s, x, y, w, h, cls, lines, tcls=None, pad=12):
        """centered multi-line text inside box; lines = [(text, cls)]"""
        s.rect(x, y, w, h, cls)
        n = len(lines); lh = 20
        y0 = y + h/2 - (n-1)*lh/2 + 5
        for i, l in enumerate(lines):
            t, c = (l, 'b fg') if isinstance(l, str) else l
            s.text(x+w/2, y0+i*lh, t, c, 'middle', maxw=w-pad*2)
    def arrow(s, x1, y1, x2, y2):
        s.add(f'<path d="M{x1} {y1} L{x2} {y2}" class="ar"/>')
        # head
        if x1 == x2:
            d = 1 if y2 > y1 else -1
            s.add(f'<path d="M{x2-5} {y2-7*d} L{x2} {y2} L{x2+5} {y2-7*d} Z" class="arh"/>')
        else:
            d = 1 if x2 > x1 else -1
            s.add(f'<path d="M{x2-7*d} {y2-5} L{x2} {y2} L{x2-7*d} {y2+5} Z" class="arh"/>')
    def head(s, title, sub):
        s.text(40, 52, title, 't fg', maxw=W-80)
        s.text(40, 80, sub, 'st muted', maxw=W-80)
    def save(s, name):
        body = '\n'.join(s.o)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {s.h}" width="{W}" height="{s.h}" role="img" aria-labelledby="ttl dsc" font-family=\'{FONTS[s.lang]}\'>\n'
               f'<title id="ttl">{escape(s.title)}</title>\n<desc id="dsc">{escape(s.desc)}</desc>\n<style>{CSS}</style>\n'
               f'<rect width="{W}" height="{s.h}" class="bg"/>\n{body}\n</svg>\n')
        open(f'{OUT}/{name}-{s.lang}.svg', 'w', encoding='utf-8').write(svg)

HOSTS = ['Claude Code', 'Codex CLI', 'Gemini / agy', 'OpenCode', 'Grok Build']

# ---------------- copy ----------------
C = {
'zh-TW': dict(
 ov_t='角色寫一次，每個工具各有一份設定', ov_s='模型、權限、工具名稱，由各工具自己決定',
 ov_l1='角色目錄', ov_l1d='每個角色寫明做什麼、能動什麼',
 ov_l2='各工具設定', ov_l2d='選哪個模型、開哪些權限、工具叫什麼名字', ov_chips=['模型','權限','工具名稱'],
 ov_l3='產生的檔案', ov_l3d='每個工具拿到自己的一整套',
 ov_foot='新增工具只要寫設定，不用寫程式',
 ov_desc='分三層。第一層是 core/ 裡的角色目錄，角色只定義一次。第二層是各工具的設定，決定模型、權限和工具名稱。第三層是為 Claude Code、Codex CLI、Gemini / agy、Grok Build、OpenCode 各自產生的檔案。新增工具只要寫設定，不用寫程式。',
 rt_t='同一個角色，每個工具用最合適的模型', rt_s='查找和快速修改用便宜的，驗證與審查用強的',
 rt_role='角色', rt_roles=[('scout','查找'),('applier','小而有界的快速修改'),('executor','需要判斷的實作'),('verifier','驗證結果'),('researcher','查外部資料'),('plan-critic','審計畫')],
 rt_inh=['沿用你自己','設定的主模型','（inherit）'], rt_lg=['便宜','中階','最強'],
 rt_foot='模型從各工具的可用清單選出；Grok Build 沿用你自己的設定',
 rt_desc='矩陣列出 scout、applier、executor、verifier、researcher、plan-critic 六個角色在五個工具上實際使用的模型。Claude Code：haiku、haiku、sonnet、opus、opus、fable。Codex CLI：gpt-6-luna、gpt-6-luna、gpt-6-astra、gpt-6-sol、gpt-6-sol、gpt-6-sol。Gemini / agy：flash、flash、pro、pro、pro、pro。OpenCode：deepseek-v4-flash、deepseek-v4-flash、gpt-5.6-luna、gpt-5.6-sol、gpt-5.6-sol、gpt-5.6-sol。Grok Build 沿用你自己設定的主模型。',
 or_t='一個需求怎麼走完', or_s='主 session 負責判斷與整合，角色只做被派的那一段',
 or_req='你的需求', or_main='主 session', or_maind='讀、判斷、整合',
 or_fast='快速路徑', or_fastt='多數工作', or_rig='嚴謹路徑', or_rigt='有風險才走',
 or_f=[('scout（可平行多個）','查找資料、讀程式'),('applier / executor','改檔'),('watcher','盯著長時間指令'),('跑一次相關檢查','改完就驗，不另派審查')],
 or_trig=['資安、不可逆或對外動作、','資料遷移、發版'],
 or_steps=[['審計畫'],['你核准'],['改檔'],['verifier','驗證']],
 or_disp='派工', or_back='結果回來', or_end='回報做了什麼、驗證了什麼',
 or_desc='你的需求進入主 session，由它讀程式、判斷並整合。快速路徑用於多數工作：scout 平行查找，applier 或 executor 改檔，watcher 盯長時間指令。嚴謹路徑只在有風險時走，也就是資安、不可逆或對外動作、資料遷移、發版：先審計畫，你核准後才改檔，最後由 verifier 驗證。結果都回到主 session，它回報做了什麼、驗證了什麼。',
 gd_t='五個工具擋同樣的事', gd_s='擋下之後都留有出口，不會把你卡死',
 gd_h=['發生什麼事','結果','出口'],
 gd_rows=[(['主 session 直接改檔'],'擋下',['寫入角色真的啟動了，','或你說 #direct']),
          (['不是 shoal 寫入角色的','agent 改檔'],'擋下',['改派 applier 或 executor']),
          (['角色再往下派工'],'擋下',['改成回報給主 session']),
          (['改完檔沒跑檢查就收工'],'問一次',['跑檢查，或說明為什麼不用'])],
 gd_foot='五個工具都強制執行',
 gd_desc='四種情況：主 session 直接改檔會被擋下，出口是寫入角色真的啟動，或你說 #direct；不是 shoal 寫入角色的 agent 改檔會被擋下，出口是改派 applier 或 executor；角色再往下派工會被擋下，出口是回報給主 session；改完檔沒跑檢查就收工會被問一次，出口是跑檢查或說明為什麼不用。五個工具都強制執行。'),
'zh-CN': dict(
 ov_t='角色只定义一次，每个工具各有一份配置', ov_s='模型、权限、工具名称，由各工具自己决定',
 ov_l1='角色目录', ov_l1d='每个角色写明做什么、能动什么',
 ov_l2='各工具配置', ov_l2d='选哪个模型、开哪些权限、工具叫什么名字', ov_chips=['模型','权限','工具名称'],
 ov_l3='生成的文件', ov_l3d='每个工具拿到自己的一整套',
 ov_foot='新增工具只要写配置，不用写代码',
 ov_desc='分三层。第一层是 core/ 里的角色目录，角色只定义一次。第二层是各工具的配置，决定模型、权限和工具名称。第三层是为 Claude Code、Codex CLI、Gemini / agy、Grok Build、OpenCode 各自生成的文件。新增工具只要写配置，不用写代码。',
 rt_t='同一个角色，每个工具用最合适的模型', rt_s='查找和快速修改用便宜的，验证与审查用强的',
 rt_role='角色', rt_roles=[('scout','查找'),('applier','小而有界的快速修改'),('executor','需要判断的实现'),('verifier','验证结果'),('researcher','查外部资料'),('plan-critic','审计划')],
 rt_inh=['沿用你自己','设置的主模型','（inherit）'], rt_lg=['便宜','中档','最强'],
 rt_foot='模型从各工具的可用列表选出；Grok Build 沿用你自己的设置',
 rt_desc='矩阵列出 scout、applier、executor、verifier、researcher、plan-critic 六个角色在五个工具上实际使用的模型。Claude Code：haiku、haiku、sonnet、opus、opus、fable。Codex CLI：gpt-6-luna、gpt-6-luna、gpt-6-astra、gpt-6-sol、gpt-6-sol、gpt-6-sol。Gemini / agy：flash、flash、pro、pro、pro、pro。OpenCode：deepseek-v4-flash、deepseek-v4-flash、gpt-5.6-luna、gpt-5.6-sol、gpt-5.6-sol、gpt-5.6-sol。Grok Build 沿用你自己设置的主模型。',
 or_t='一个需求怎么走完', or_s='主 session 负责判断与整合，角色只做被派的那一段',
 or_req='你的需求', or_main='主 session', or_maind='读、判断、整合',
 or_fast='快速路径', or_fastt='多数工作', or_rig='严谨路径', or_rigt='有风险才走',
 or_f=[('scout（可并行多个）','查找资料、读代码'),('applier / executor','改文件'),('watcher','盯着长时间命令'),('跑一次相关检查','改完就验，不另派审查')],
 or_trig=['安全、不可逆或对外操作、','数据迁移、发版'],
 or_steps=[['审计划'],['你批准'],['改文件'],['verifier','验证']],
 or_disp='派工', or_back='结果回来', or_end='汇报做了什么、验证了什么',
 or_desc='你的需求进入主 session，由它读代码、判断并整合。快速路径用于多数工作：scout 并行查找，applier 或 executor 改文件，watcher 盯长时间命令。严谨路径只在有风险时走，也就是安全、不可逆或对外操作、数据迁移、发版：先审计划，你批准后才改文件，最后由 verifier 验证。结果都回到主 session，它汇报做了什么、验证了什么。',
 gd_t='五个工具拦同样的事', gd_s='拦下之后都留有出口，不会把你卡死',
 gd_h=['发生什么事','结果','出口'],
 gd_rows=[(['主 session 直接改文件'],'拦下',['写入角色真的启动了，','或你说 #direct']),
          (['不是 shoal 写入角色的','agent 改文件'],'拦下',['改派 applier 或 executor']),
          (['角色再往下派工'],'拦下',['改成汇报给主 session']),
          (['改完文件没跑检查就收工'],'问一次',['跑检查，或说明为什么不用'])],
 gd_foot='五个工具都强制执行',
 gd_desc='四种情况：主 session 直接改文件会被拦下，出口是写入角色真的启动，或你说 #direct；不是 shoal 写入角色的 agent 改文件会被拦下，出口是改派 applier 或 executor；角色再往下派工会被拦下，出口是汇报给主 session；改完文件没跑检查就收工会被问一次，出口是跑检查或说明为什么不用。五个工具都强制执行。'),
'en': dict(
 ov_t='Define roles once. Every tool gets its own setup.', ov_s='Model, permissions and tool names are resolved per tool',
 ov_l1='Role catalog', ov_l1d='Each role says what it does and what it may touch',
 ov_l2='Per-tool settings', ov_l2d='Which model, which permissions, what the tools are called', ov_chips=['Model','Permissions','Tool names'],
 ov_l3='Generated files', ov_l3d='Each tool gets its own full set',
 ov_foot='Adding a tool is configuration, not code',
 ov_desc='Three layers. The first is the role catalog in core/, where each role is defined once. The second is per-tool settings that choose the model, permissions and tool names. The third is the files generated for Claude Code, Codex CLI, Gemini / agy, OpenCode and Grok Build. Adding a tool is configuration, not code.',
 rt_t='Same role, the right model on every tool', rt_s='Cheap models for lookups and small edits, strong ones for checking and review',
 rt_role='Role', rt_roles=[('scout','lookups'),('applier','small, bounded'),('executor','needs judgment'),('verifier','checks the result'),('researcher','outside research'),('plan-critic','reviews the plan')],
 rt_inh=['Uses your own','main model','(inherit)'], rt_lg=['Budget','Mid','Strongest'],
 rt_foot="Models are picked from each tool's available list; Grok Build keeps the model you set",
 rt_desc='A matrix of the models actually used by six roles on five tools. Claude Code: haiku, haiku, sonnet, opus, opus, fable for scout, applier, executor, verifier, researcher, plan-critic. Codex CLI: gpt-6-luna, gpt-6-luna, gpt-6-astra, gpt-6-sol, gpt-6-sol, gpt-6-sol. Gemini / agy: flash, flash, pro, pro, pro, pro. OpenCode: deepseek-v4-flash, deepseek-v4-flash, gpt-5.6-luna, gpt-5.6-sol, gpt-5.6-sol, gpt-5.6-sol. Grok Build uses the main model you set yourself.',
 or_t='How one request gets done', or_s='The main session decides and integrates; roles do only the part they are given',
 or_req='Your request', or_main='Main session', or_maind='reads, decides, integrates',
 or_fast='Fast path', or_fastt='most work', or_rig='Rigorous path', or_rigt='only when there is risk',
 or_f=[('scouts, several in parallel','look things up, read code'),('applier / executor','edit files'),('watcher','keeps an eye on long commands'),('One targeted check','verify the change, no extra review')],
 or_trig=['Security, irreversible or external','actions, data migration, release'],
 or_steps=[['Review','plan'],['You','approve'],['Edit','files'],['verifier','checks']],
 or_disp='dispatches', or_back='results come back', or_end='Reports what was done and what was verified',
 or_desc='Your request goes to the main session, which reads, decides and integrates. The fast path covers most work: scouts look things up in parallel, applier or executor edit files, watcher keeps an eye on long commands. The rigorous path runs only when there is risk, meaning security, irreversible or external actions, data migration or a release: review the plan, you approve, edit, then verifier checks. All results return to the main session, which reports what was done and what was verified.',
 gd_t='Every tool blocks the same things', gd_s='Each block comes with a way out, so you are never stuck',
 gd_h=['What happens','Result','Way out'],
 gd_rows=[(['Main session edits files directly'],'Blocked',['A write role has really started,','or you say #direct']),
          (['An agent that is not a shoal','write role edits files'],'Blocked',['Hand the edit to applier or executor']),
          (['A role dispatches another agent'],'Blocked',['Report back to the main session']),
          (['Turn ends after changes,','with no check run'],'Asked once',['Run a check, or say why none is needed'])],
 gd_foot='Enforced on all five tools',
 gd_desc='Four cases. The main session editing files directly is blocked; the way out is a write role that really started, or you say #direct. An agent that is not a shoal write role editing files is blocked; hand the edit to applier or executor. A role dispatching another agent is blocked; report back to the main session. Ending a turn after changes with no check run is asked about once; run a check or say why none is needed. Enforced on all five tools.'),
}

def overview(lang):
    c = C[lang]; s = S(lang, 560, c['ov_t'], c['ov_desc']); s.head(c['ov_t'], c['ov_s'])
    rows = [(110, 'sb', c['ov_l1'], 'core/', c['ov_l1d']), (250, 'sp', c['ov_l2'], 'hosts/', c['ov_l2d']), (390, 'sg', c['ov_l3'], '', c['ov_l3d'])]
    for i, (y, cls, nm, path, d) in enumerate(rows):
        s.rect(40, y, 880, 104, 'card', 14)
        s.rect(40, y+16, 5, 72, cls, 2)
        s.text(66, y+38, nm, 'h fg', maxw=200)
        if path:
            pw = wid(path, 13, True) + 20
            s.rect(66, y+54, pw, 26, cls, 13); s.text(66+pw/2, y+72, path, 'sm mono fg', 'middle')
        s.text(290, y+32, d, 'b muted', maxw=610)
        if i == 0:
            x = 290
            for r in ['scout', 'applier', 'executor', 'verifier', 'researcher', '…']:
                w = wid(r, 14, True) + 26
                s.rect(x, y+50, w, 34, cls, 17); s.text(x+w/2, y+72, r, 'b mono fg', 'middle'); x += w + 10
        elif i == 1:
            x = 290
            for r in c['ov_chips']:
                w = max(wid(r, 15) + 36, 110)
                s.rect(x, y+50, w, 34, cls, 17); s.text(x+w/2, y+72, r, 'b fg', 'middle', maxw=w-12); x += w + 12
        else:
            cw = (610 - 4*10) / 5; x = 290
            for hname in HOSTS:
                s.rect(x, y+50, cw, 34, cls, 17); s.text(x+cw/2, y+72, hname, 'sm bold fg', 'middle', maxw=cw-10); x += cw + 10
    s.arrow(480, 214, 480, 246); s.arrow(480, 354, 480, 386)
    s.text(480, 520, c['ov_foot'], 'h fg', 'middle', maxw=860)
    s.save('shoal-overview')

MODELS = {  # source: tools/render.py --explain @ b566017
 'Claude Code': ['haiku','haiku','sonnet','opus','opus','fable'],
 'Codex CLI':   ['gpt-6-luna','gpt-6-luna','gpt-6-astra','gpt-6-sol','gpt-6-sol','gpt-6-sol'],
 'Gemini / agy':['flash','flash','pro','pro','pro','pro'],
 'OpenCode':    ['deepseek-v4-flash','deepseek-v4-flash','gpt-5.6-luna','gpt-5.6-sol','gpt-5.6-sol','gpt-5.6-sol'],
}
TIER = {'haiku':'sg','flash':'sg','gpt-6-luna':'sg','deepseek-v4-flash':'sg','sonnet':'sa','gpt-6-astra':'sa','gpt-5.6-luna':'sa'}
def routing(lang):
    c = C[lang]; H = 130 + 48 + 6*58 + 90
    s = S(lang, H, c['rt_t'], c['rt_desc']); s.head(c['rt_t'], c['rt_s'])
    x0, rw, cw, y0, hh, rh = 40, 160, 144, 112, 46, 58
    s.text(x0+8, y0+hh/2+5, c['rt_role'], 'b muted')
    cols = HOSTS
    for j, hname in enumerate(cols):
        x = x0 + rw + j*cw
        s.text(x+cw/2, y0+hh/2+5, hname, 'h fg', 'middle', maxw=cw-8)
    s.add(f'<path d="M{x0} {y0+hh} H{x0+rw+5*cw}" class="ln"/>')
    for i, (rn, rd) in enumerate(c['rt_roles']):
        y = y0 + hh + 6 + i*rh
        s.text(x0+8, y+25, rn, 'b mono bold fg', maxw=rw-12)
        s.text(x0+8, y+44, rd, 'sm muted', maxw=rw-12)
        for j, hname in enumerate(cols[:4]):
            m = MODELS[hname][i]
            x = x0 + rw + j*cw + 5
            s.rect(x, y+3, cw-10, rh-10, TIER.get(m, 'sp'), 8)
            s.text(x+(cw-10)/2, y+rh/2+3, m, 'xs mono bold fg', 'middle', maxw=cw-12)
    gx = x0 + rw + 4*cw + 5
    gh = 6*rh - 10
    s.rect(gx, y0+hh+6+3, cw-10, gh, 'sx', 8)
    for k, line in enumerate(c['rt_inh']):
        s.text(gx+(cw-10)/2, y0+hh+6+3+gh/2-22+k*22+5, line, 'sm fg' if k < 2 else 'sm mono muted', 'middle', maxw=cw-14)
    ly = y0 + hh + 6 + 6*rh + 22
    x = x0
    for cls, lab in zip(['sg','sa','sp'], c['rt_lg']):
        s.rect(x, ly-13, 18, 18, cls, 5); s.text(x+26, ly+1, lab, 'sm fg', maxw=120); x += 26 + wid(lab, 13) + 24
    s.text(x0, ly+34, c['rt_foot'], 'sm muted', maxw=880)
    s.save('shoal-routing')

def orchestration(lang):
    c = C[lang]; s = S(lang, 774, c['or_t'], c['or_desc']); s.head(c['or_t'], c['or_s'])
    s.box(380, 104, 200, 44, 'sb', [c['or_req']])
    s.arrow(480, 148, 480, 176)
    s.rect(220, 178, 520, 74, 'card', 14)
    s.text(480, 212, c['or_main'], 'h fg', 'middle'); s.text(480, 236, c['or_maind'], 'b muted', 'middle', maxw=480)
    # branches
    s.add('<path d="M480 252 V272 M250 272 H710 M250 272 V296 M710 272 V296" class="ln"/>')
    s.text(496, 268, c['or_disp'], 'sm muted', maxw=100)
    for (lx, cls, nm, tag) in [(40, 'sg', c['or_fast'], c['or_fastt']), (500, 'sa', c['or_rig'], c['or_rigt'])]:
        s.rect(lx, 298, 420, 370, 'card', 14); pass
        s.text(lx+20, 334, nm, 'h fg', maxw=170)
        tw = wid(tag, 13) + 22
        s.rect(lx+400-tw, 316, tw, 26, cls, 13); s.text(lx+400-tw/2, 334, tag, 'sm fg', 'middle', maxw=tw-8)
    for i, (a, b) in enumerate(c['or_f']):
        y = 360 + i*74
        s.rect(60, y, 380, 62, 'sg', 10)
        s.text(78, y+26, a, 'b bold fg' if i else 'b bold fg', maxw=345); s.text(78, y+47, b, 'sm muted', maxw=345)
    s.rect(520, 360, 380, 66, 'sa', 10)
    s.text(710, 388, c['or_trig'][0], 'b fg', 'middle', maxw=350); s.text(710, 411, c['or_trig'][1], 'b fg', 'middle', maxw=350)
    x = 520
    for k, st in enumerate(c['or_steps']):
        s.box(x, 458, 80, 66, 'sa' if k < 3 else 'sp', [(t, ('sm mono bold fg' if t == 'verifier' else 'b fg')) for t in st], pad=6)
        if k < 3: s.arrow(x+80, 491, x+100, 491)
        x += 100
    s.text(710, 552, '', 'sm muted')
    # converge
    s.add('<path d="M250 668 V694 M710 668 V694 M250 694 H710 M480 694 V710" class="ln"/>')
    s.text(496, 690, c['or_back'], 'sm muted', maxw=140)
    s.arrow(480, 704, 480, 724)
    s.rect(200, 726, 560, 38, 'card', 12)
    s.text(480, 751, c['or_end'], 'h fg', 'middle', maxw=520)
    s.save('shoal-orchestration')

def guard(lang):
    c = C[lang]; s = S(lang, 620, c['gd_t'], c['gd_desc']); s.head(c['gd_t'], c['gd_s'])
    xs = (40, 400, 520); ws = (340, 110, 400)
    for x, h in zip(xs, c['gd_h']):
        s.text(x+16, 124, h, 'b muted bold', maxw=300)
    s.add('<path d="M40 136 H920" class="ln"/>')
    for i, (sit, res, way) in enumerate(c['gd_rows']):
        y = 148 + i*92
        s.rect(40, y, 880, 80, 'card', 14)
        s.box(52, y+8, 330, 64, 'sx', [(t, 'b fg') for t in sit], pad=8) if False else None
        n = len(sit)
        for k, t in enumerate(sit):
            s.text(56, y+40+(k-(n-1)/2)*21, t, 'b fg', maxw=320)
        rcls = 'sr' if res in ('擋下', '拦下', 'Blocked') else 'sa'
        s.box(404, y+22, 100, 36, rcls, [(res, 'b bold fg')], pad=6)
        s.arrow(374, y+40, 398, y+40)
        n = len(way)
        for k, t in enumerate(way):
            s.text(536, y+40+(k-(n-1)/2)*21, t, 'b fg', maxw=370)
        s.add(f'<path d="M524 {y+14} V{y+66}" class="ln"/>')
    fy = 148 + 4*92 + 14
    s.text(40, fy+22, c['gd_foot'], 'h fg', maxw=260)
    x = 40 + wid(c['gd_foot'], 16) + 24
    for hname in HOSTS:
        w = wid(hname, 13) + 22
        s.rect(x, fy, w, 32, 'sg', 16); s.text(x+w/2, fy+21, hname, 'sm bold fg', 'middle'); x += w + 8
    assert x < 930, (lang, x)
    s.save('shoal-guard')

for l in C:
    overview(l); routing(l); orchestration(l); guard(l)
print('ok')
