# -*- coding: utf-8 -*-
"""panel.html 界面重构：仅替换样式与结构，脚本逻辑原样保留（含 make_assets 依赖的片段）。"""
import io

P = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html"
h = io.open(P, encoding="utf-8").read()

# ---------------- 1. 样式 ----------------
CSS = r"""
  :root{
    --bg:#eef2f8; --bg2:#fafcff;
    --card:#fff; --line:#e4eaf3; --soft:#f4f7fc;
    --text:#0f1a26; --muted:#6b7b8c; --faint:#9dabb9;
    --brand:#0b63c5; --brand2:#1180e8; --brand-soft:#e9f1fd;
    --ok:#0f8a5f; --ok-soft:#e4f6ee;
    --warn:#a9650f; --warn-soft:#fdf2e3;
    --err:#c8403f; --err-soft:#fdeceb;
    --hero1:#1470d8; --hero2:#0a4a9c;
    --hdr:rgba(247,249,252,.82); --hdrline:rgba(226,233,242,.9);
    --r:16px;
    --sh:0 1px 2px rgba(15,26,38,.04), 0 12px 28px -20px rgba(15,26,38,.55);
  }
  @media (prefers-color-scheme:dark){
    :root{
      --bg:#0c1219; --bg2:#141d27;
      --card:#151e29; --line:#243242; --soft:#1a2532;
      --text:#e9eff7; --muted:#94a4b6; --faint:#6d7d8f;
      --brand:#5aa2f0; --brand2:#7cb8f7; --brand-soft:rgba(90,162,240,.16);
      --ok:#3ecf8e; --ok-soft:rgba(62,207,142,.15);
      --warn:#e2b06b; --warn-soft:rgba(226,176,107,.14);
      --err:#f07171; --err-soft:rgba(240,113,113,.14);
      --hero1:#1a5ca8; --hero2:#0d335f;
      --hdr:rgba(12,18,25,.78); --hdrline:rgba(36,50,66,.9);
      --sh:0 1px 2px rgba(0,0,0,.35), 0 14px 32px -22px rgba(0,0,0,.9);
    }
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html{-webkit-text-size-adjust:100%}
  body{
    margin:0;color:var(--text);
    background:radial-gradient(1200px 520px at 50% -180px, var(--bg2), var(--bg));
    background-attachment:fixed;
    font:15px/1.55 -apple-system,"SF Pro Text","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    padding:0 0 env(safe-area-inset-bottom);
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:760px;margin:0 auto;padding:0 16px 44px}
  .num{font-variant-numeric:tabular-nums}

  /* ---------- 登录 ---------- */
  .login{
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;
    background:radial-gradient(680px 360px at 50% 6%, var(--brand-soft), transparent 70%);
  }
  .login-card{
    width:100%;max-width:366px;background:var(--card);border:1px solid var(--line);
    border-radius:22px;padding:32px 24px 22px;box-shadow:var(--sh);
  }
  .mark{
    width:52px;height:52px;border-radius:16px;background:linear-gradient(150deg,var(--brand2),var(--hero2));
    color:#fff;display:grid;place-items:center;font-weight:700;font-size:21px;
    margin:0 auto 16px;box-shadow:0 10px 22px -10px rgba(11,99,197,.85);
  }
  .login-card h1{font-size:19px;margin:0 0 5px;text-align:center;font-weight:680;letter-spacing:-.2px}
  .login-card .sub{text-align:center;color:var(--muted);font-size:12px;margin:0 0 24px}
  label.f{display:block;font-size:12.5px;color:var(--muted);margin-bottom:7px}
  input[type=password],input[type=text],input[type=number]{
    width:100%;font:inherit;padding:12px 14px;border:1px solid var(--line);border-radius:12px;
    background:var(--soft);outline:none;transition:border-color .15s, box-shadow .15s, background .15s;
    color:var(--text);appearance:none;
  }
  input::placeholder{color:var(--faint)}
  input:focus{border-color:var(--brand);background:var(--card);box-shadow:0 0 0 3px var(--brand-soft)}
  .btn{
    width:100%;font:inherit;font-size:15px;font-weight:620;padding:13px;border-radius:12px;
    border:1px solid var(--brand);background:linear-gradient(160deg,var(--brand2),var(--brand));
    color:#fff;cursor:pointer;margin-top:16px;transition:transform .12s, opacity .15s;
    box-shadow:0 10px 22px -12px rgba(11,99,197,.95);
  }
  .btn:active{transform:scale(.985)}
  .btn[disabled]{opacity:.6}
  .err{color:var(--err);font-size:12.5px;margin-top:12px;min-height:18px;text-align:center;line-height:1.6}
  .tip{font-size:11.5px;color:var(--faint);text-align:center;margin-top:18px;line-height:1.75}
  .host-tip{margin-top:6px;cursor:pointer}
  .host-tip b{color:var(--muted);font-weight:600}
  #diagBox{
    margin:10px 0 0;padding:11px;border:1px solid var(--line);border-radius:12px;background:var(--soft);
    font:10.5px/1.55 ui-monospace,Menlo,Consolas,monospace;color:var(--muted);white-space:pre-wrap;
    word-break:break-all;max-height:230px;overflow:auto;-webkit-user-select:text;user-select:text;
    display:none;
  }

  /* ---------- 顶栏 ---------- */
  header{
    position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;
    margin:0 -16px 12px;padding:calc(10px + env(safe-area-inset-top)) 16px 12px;
    background:var(--hdr);backdrop-filter:saturate(160%) blur(12px);
    -webkit-backdrop-filter:saturate(160%) blur(12px);
    border-bottom:1px solid var(--hdrline);
  }
  .logo{
    width:40px;height:40px;border-radius:13px;background:linear-gradient(150deg,var(--brand2),var(--hero2));
    color:#fff;display:grid;place-items:center;font-weight:700;font-size:17px;flex:0 0 auto;
    box-shadow:0 8px 18px -10px rgba(11,99,197,.9);
  }
  .h-main{min-width:0;flex:1}
  .h-main h1{font-size:16.5px;margin:0;font-weight:660;letter-spacing:-.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .h-main .meta{font-size:11.5px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);display:inline-block;margin-right:5px;vertical-align:1px}
  .icon-btn{
    width:38px;height:38px;border-radius:12px;border:1px solid var(--line);background:var(--card);
    display:grid;place-items:center;cursor:pointer;color:var(--muted);flex:0 0 auto;box-shadow:var(--sh);
  }
  .icon-btn:active{background:var(--soft);color:var(--brand)}
  .spin{animation:sp .8s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}

  /* ---------- 外网大卡片 ---------- */
  .hero{
    position:relative;overflow:hidden;border-radius:20px;padding:17px 16px 13px;margin-bottom:12px;color:#fff;
    background:linear-gradient(155deg,var(--hero1),var(--hero2));
    box-shadow:0 18px 36px -22px rgba(10,74,156,.9);
  }
  .hero:after{
    content:"";position:absolute;right:-70px;top:-110px;width:210px;height:210px;border-radius:50%;
    background:radial-gradient(circle at 35% 35%,rgba(255,255,255,.24),transparent 62%);
  }
  .hero-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px}
  .hero-t{font-size:11.5px;font-weight:600;letter-spacing:.5px;color:rgba(255,255,255,.76)}
  .badge{
    display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;
    padding:3px 9px;border-radius:20px;background:var(--ok-soft);color:var(--ok);
  }
  .badge.off{background:var(--soft);color:var(--faint)}
  .hero .badge{background:rgba(255,255,255,.17);color:#fff;backdrop-filter:blur(4px)}
  .hero .badge.off{background:rgba(255,255,255,.12);color:rgba(255,255,255,.72)}
  .rates{display:flex;gap:10px}
  .rate{flex:1;background:var(--soft);border-radius:12px;padding:11px 12px}
  .rate .k{font-size:11px;color:var(--muted)}
  .rate .v{font-size:20px;font-weight:660;margin-top:3px;letter-spacing:-.4px}
  .rate .v small{font-size:11px;font-weight:500;color:var(--muted);margin-left:2px}
  .hero .rate{background:rgba(255,255,255,.13)}
  .hero .rate .k{color:rgba(255,255,255,.7)}
  .hero .rate .v{color:#fff}
  .hero .rate .v small{color:rgba(255,255,255,.72)}
  #wanSpark{width:100%;height:42px;display:block;margin:6px 0 6px}
  .hero-foot{display:flex;gap:20px;border-top:1px solid rgba(255,255,255,.18);padding-top:10px}
  .hero-foot div{min-width:0;flex:1}
  .hero-foot span{display:block;font-size:10.5px;color:rgba(255,255,255,.62);margin-bottom:1px}
  .hero-foot b{display:block;font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

  /* ---------- 卡片 ---------- */
  .card{
    background:var(--card);border:1px solid var(--line);border-radius:var(--r);
    padding:15px 16px;margin-bottom:12px;box-shadow:var(--sh);
  }
  .card-h{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:11px}
  .card-h h2{font-size:12.5px;margin:0;font-weight:660;color:var(--text);letter-spacing:.2px;display:flex;align-items:center}
  .card-h h2:before{
    content:"";width:3px;height:12px;border-radius:2px;flex:0 0 auto;margin-right:8px;
    background:linear-gradient(var(--brand2),var(--brand));
  }
  .card-h .ext{font-size:11.5px;color:var(--faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

  /* ---------- 键值 ---------- */
  .kv{display:grid;grid-template-columns:1fr 1fr;gap:12px 14px;font-size:12.5px}
  .kv div{min-width:0}
  .kv .k{color:var(--faint);font-size:10.5px;margin-bottom:3px}
  .kv .v{font-weight:560;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .divider{height:1px;background:var(--line);margin:16px 0 13px}

  /* ---------- WiFi ---------- */
  .wifi-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .wifi{border:1px solid var(--line);border-radius:13px;padding:12px;background:var(--soft)}
  .wifi.off{opacity:.62}
  .wifi-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
  .band{font-size:10.5px;font-weight:700;letter-spacing:.4px;padding:2px 7px;border-radius:6px}
  .band.b24{background:#fdf1e2;color:#a9650f}
  .band.b5{background:#e9f1fd;color:#0b63c5}
  @media (prefers-color-scheme:dark){
    .band.b24{background:rgba(226,176,107,.16);color:#e2b06b}
    .band.b5{background:rgba(90,162,240,.16);color:#7cb8f7}
  }
  .wifi .ssid{font-size:13.5px;font-weight:650;margin-bottom:4px;word-break:break-all;line-height:1.35}
  .wifi .info{font-size:11px;color:var(--muted);line-height:1.6}
  .wifi .st{font-size:10.5px;font-weight:600;color:var(--ok)}
  .wifi.off .st{color:var(--faint)}
  .wifi .edit{
    margin-top:9px;width:100%;font:inherit;font-size:11.5px;font-weight:600;padding:7px;
    border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--brand);cursor:pointer;
  }
  .wifi .edit:active{background:var(--brand-soft)}

  /* ---------- 设备列表 ---------- */
  #devList{display:flex;flex-direction:column}
  .dev{
    display:flex;align-items:center;gap:11px;padding:9px;margin:0 -9px;border-radius:12px;
    cursor:pointer;transition:background .12s;
  }
  .dev+.dev{margin-top:1px}
  .dev:active{background:var(--soft)}
  .av{
    width:38px;height:38px;border-radius:12px;background:var(--brand-soft);color:var(--brand);
    display:grid;place-items:center;font-size:14px;font-weight:650;flex:0 0 auto;
  }
  .av.c0{background:#e8f0fe;color:#2563c9}
  .av.c1{background:#e4f6ee;color:#0f8a5f}
  .av.c2{background:#fdf1e2;color:#a9650f}
  .av.c3{background:#f0ecfd;color:#6b46d5}
  .av.c4{background:#fdecef;color:#c2417a}
  .av.c5{background:#e7f5fb;color:#0b7396}
  @media (prefers-color-scheme:dark){
    .av.c0{background:rgba(37,99,201,.22);color:#8ab4f8}
    .av.c1{background:rgba(15,138,95,.22);color:#69d3a2}
    .av.c2{background:rgba(169,101,15,.24);color:#e2b06b}
    .av.c3{background:rgba(107,70,213,.24);color:#b39cf7}
    .av.c4{background:rgba(194,65,122,.24);color:#ef9ab8}
    .av.c5{background:rgba(11,115,150,.24);color:#6fc7de}
  }
  .av.lg{width:44px;height:44px;border-radius:14px;font-size:17px}
  .dev-main{min-width:0;flex:1}
  .dev-main .n{font-size:13.5px;font-weight:560;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .dev-main .s{font-size:10.5px;color:var(--faint);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.1px}
  .dev-r{text-align:right;flex:0 0 auto;max-width:38%}
  .dev-r .ip{font-size:11.5px;font-weight:560;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .dev-r .t{font-size:10.5px;color:var(--faint);margin-top:2px;white-space:nowrap}
  .chev{color:var(--faint);font-size:17px;line-height:1;margin-left:-2px;flex:0 0 auto;opacity:.7}
  .mtag{display:inline-block;font-size:9.5px;padding:1px 5px;border-radius:5px;background:var(--card);color:var(--muted);margin-right:6px;vertical-align:1px;border:1px solid var(--line)}
  .dev .n em.limtag{
    font-style:normal;font-size:9.5px;font-weight:700;color:var(--warn);
    background:var(--warn-soft);padding:1px 5px;border-radius:5px;margin-left:4px;vertical-align:1px;
  }
  .empty{font-size:12.5px;color:var(--faint);padding:8px 0 4px}
  #dvSpark{width:100%;height:66px;display:block;margin:6px 0 8px}
  .info{font-size:11.5px;color:var(--muted);line-height:1.6}

  /* ---------- 维护 ---------- */
  .maint{display:flex;align-items:center;gap:12px}
  .maint-l{flex:1;min-width:0}
  .maint-l b{display:block;font-size:13.5px;font-weight:600}
  .maint-l span{display:block;font-size:11px;color:var(--faint);margin-top:2px;line-height:1.5}

  /* ---------- 弹层 ---------- */
  .mask{
    position:fixed;inset:0;background:rgba(9,16,26,.44);display:flex;align-items:flex-end;
    justify-content:center;z-index:50;backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);
  }
  .sheet{
    width:100%;max-width:520px;background:var(--card);border-radius:22px 22px 0 0;
    padding:10px 18px calc(18px + env(safe-area-inset-bottom));animation:up .24s cubic-bezier(.2,.8,.3,1);
    max-height:92vh;overflow:auto;box-shadow:0 -14px 44px rgba(6,12,22,.3);
  }
  .sheet:before{
    content:"";display:block;width:38px;height:4px;border-radius:3px;background:var(--line);margin:2px auto 15px;
  }
  @keyframes up{from{transform:translateY(26px);opacity:.5}}
  .sheet h3{font-size:16.5px;margin:0 0 2px;font-weight:670;letter-spacing:-.2px}
  .sheet .sub2{font-size:11.5px;color:var(--faint);margin:0 0 16px}
  .dv-head{display:flex;align-items:center;gap:12px;margin-bottom:15px}
  .dv-head h3{margin:0}
  .dv-head .sub2{margin:2px 0 0;letter-spacing:.3px}
  .field{margin-bottom:13px}
  .field label{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--muted);margin-bottom:6px}
  .field label button{
    background:none;border:none;color:var(--brand);font:inherit;font-size:11.5px;
    cursor:pointer;padding:2px 0;font-weight:600;
  }
  .kv2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .input-unit{position:relative}
  .input-unit input{padding-right:48px}
  .input-unit span{position:absolute;right:12px;top:50%;transform:translateY(-50%);font-size:11px;color:var(--faint);pointer-events:none}
  .chips{display:flex;gap:6px;margin-top:7px;flex-wrap:wrap}
  .chip{
    font:inherit;font-size:11px;font-weight:560;padding:5px 10px;border-radius:8px;
    border:1px solid var(--line);background:var(--soft);color:var(--muted);cursor:pointer;
  }
  .chip:active{background:var(--brand-soft);color:var(--brand);border-color:transparent}
  .row{display:flex;align-items:center;justify-content:space-between;padding:10px 0}
  .row .lbl{font-size:13.5px}
  .row .lbl small{display:block;color:var(--faint);font-size:11px;font-weight:400;margin-top:2px}
  .sw{position:relative;width:46px;height:27px;flex:0 0 auto}
  .sw input{opacity:0;width:0;height:0;position:absolute}
  .sw i{position:absolute;inset:0;background:var(--line);border-radius:20px;transition:.18s;cursor:pointer}
  .sw i:before{
    content:"";position:absolute;width:21px;height:21px;border-radius:50%;background:#fff;
    left:3px;top:3px;transition:.18s;box-shadow:0 1px 3px rgba(0,0,0,.22);
  }
  .sw input:checked + i{background:var(--brand)}
  .sw input:checked + i:before{transform:translateX(19px)}
  .sheet-btns{display:flex;gap:10px;margin-top:18px}
  .btn2{
    flex:1;font:inherit;font-weight:600;padding:12px;border-radius:12px;border:1px solid var(--line);
    background:var(--card);color:var(--text);cursor:pointer;transition:opacity .15s;
  }
  .btn2.pri{background:linear-gradient(160deg,var(--brand2),var(--brand));border-color:transparent;color:#fff;box-shadow:0 10px 20px -12px rgba(11,99,197,.95)}
  .btn2.danger{background:var(--card);border-color:rgba(201,64,63,.35);color:var(--err)}
  .btn2.sm{flex:0 0 auto;width:auto;padding:9px 16px;font-size:13px}
  .btn2[disabled]{opacity:.55}
  .sheet .err{text-align:left;margin-top:10px}
  .note{
    background:var(--warn-soft);color:var(--warn);font-size:11.5px;line-height:1.65;
    padding:10px 12px;border-radius:11px;margin-top:4px;
  }
  .toast{
    position:fixed;left:50%;bottom:34px;transform:translateX(-50%);z-index:80;
    background:rgba(12,20,30,.94);color:#fff;font-size:12.5px;padding:11px 18px;border-radius:22px;
    opacity:0;transition:.22s;pointer-events:none;max-width:82vw;text-align:center;
    box-shadow:0 12px 28px rgba(0,0,0,.28);
  }
  .toast.show{opacity:1;transform:translate(-50%,-6px)}

  /* ---------- 页脚 ---------- */
  .foot{text-align:center;margin-top:20px;padding-bottom:6px}
  .foot-meta{font-size:11px;color:var(--faint);line-height:1.9}
  .linkbtn{
    margin-top:10px;background:none;border:1px solid var(--line);border-radius:10px;
    color:var(--muted);font:inherit;font-size:11.5px;padding:7px 16px;cursor:pointer;
  }
  .linkbtn:active{background:var(--soft)}
  .skel{height:14px;border-radius:6px;background:linear-gradient(90deg,var(--soft),var(--card),var(--soft));
    background-size:200% 100%;animation:sh 1.2s infinite;margin:6px 0}
  @keyframes sh{to{background-position:-200% 0}}
  .hidden{display:none!important}
"""

i0 = h.index("<style>") + len("<style>")
i1 = h.index("</style>")
h = h[:i0] + "\n" + CSS + "\n" + h[i1:]

# ---------------- 2. 登录页 ----------------
LOGIN = """<!-- 登录 -->
<div class="login" id="viewLogin">
  <div class="login-card">
    <div class="mark">Z</div>
    <h1>中兴路由管家</h1>
    <p class="sub">巡天 BE5100 Pro+ · ZXSLC SR7110</p>
    <label class="f" for="pwd">管理员密码</label>
    <input id="pwd" type="password" placeholder="路由器背面标签上的密码" autocomplete="current-password">
    <button class="btn" id="btnLogin">登录</button>
    <div class="err" id="loginErr"></div>
    <p class="tip">密码只发给你家里的路由器，不经过任何服务器。<br>电脑需与本路由处于同一网络。</p>
  </div>
</div>

"""
a = h.index("<!-- 登录 -->")
b = h.index("<!-- 主界面 -->")
h = h[:a] + LOGIN + h[b:]

# ---------------- 3. 主界面 ----------------
MAIN = """<!-- 主界面 -->
<div class="wrap hidden" id="viewMain">
  <header>
    <div class="logo">Z</div>
    <div class="h-main">
      <h1 id="devName">连接中…</h1>
      <div class="meta" id="devMeta">—</div>
    </div>
    <div class="icon-btn" id="btnRefresh" title="刷新">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5V2L7 6l5 4V7a5 5 0 11-5 5H5a7 7 0 107-7z"/></svg>
    </div>
  </header>

  <section class="hero">
    <div class="hero-h">
      <span class="hero-t">外网连接</span>
      <span class="badge" id="wanBadge"><span class="dot"></span>已连接</span>
    </div>
    <div class="rates">
      <div class="rate"><div class="k">↓ 下行速率</div><div class="v" id="rateDown">—</div></div>
      <div class="rate"><div class="k">↑ 上行速率</div><div class="v" id="rateUp">—</div></div>
    </div>
    <svg id="wanSpark" viewBox="0 0 300 42" preserveAspectRatio="none" aria-hidden="true"></svg>
    <div class="hero-foot">
      <div><span>WAN IP</span><b class="num" id="wanIp">—</b></div>
      <div><span>拨号方式</span><b id="wanType">—</b></div>
    </div>
  </section>

  <section class="card">
    <div class="card-h"><h2>连接详情</h2><span class="ext" id="runTime">—</span></div>
    <div class="kv">
      <div><div class="k">宽带账号</div><div class="v" id="wanUser">—</div></div>
      <div><div class="k">协商速率</div><div class="v" id="wanSpeed">—</div></div>
      <div><div class="k">局域网网关</div><div class="v num" id="lanIp">—</div></div>
      <div><div class="k">在线时长</div><div class="v" id="wanUptime">—</div></div>
    </div>
  </section>

  <section class="card">
    <div class="card-h"><h2>无线网络</h2><span class="ext" id="wifiCount">—</span></div>
    <div class="wifi-grid" id="wifiGrid"></div>
  </section>

  <section class="card">
    <div class="card-h"><h2>在线设备</h2><span class="ext" id="devCount">—</span></div>
    <div id="devList"></div>
  </section>

  <section class="card">
    <div class="card-h"><h2>路由器维护</h2><span class="ext">谨慎操作</span></div>
    <div class="maint">
      <div class="maint-l">
        <b>重启路由器</b>
        <span>所有设备断网约 1–2 分钟，宽带配置不会丢失</span>
      </div>
      <button class="btn2 danger sm" id="btnReboot">重启</button>
    </div>
  </section>

  <div class="foot" id="foot"></div>
</div>

"""
a = h.index("<!-- 主界面 -->")
b = h.index("<!-- 修改 WiFi -->")
h = h[:a] + MAIN + h[b:]

# ---------------- 4. 设备详情弹层 ----------------
DEV = """<!-- 设备详情 / 限速 -->
<div class="mask hidden" id="devSheet">
  <div class="sheet">
    <div class="dv-head">
      <div class="av lg" id="dvAv">?</div>
      <div style="min-width:0;flex:1">
        <h3 id="dvName">设备</h3>
        <p class="sub2" id="dvSub">—</p>
      </div>
    </div>

    <div class="rates">
      <div class="rate"><div class="k">↓ 当前下载</div><div class="v" id="dvDown">—</div></div>
      <div class="rate"><div class="k">↑ 当前上传</div><div class="v" id="dvUp">—</div></div>
    </div>
    <svg id="dvSpark" viewBox="0 0 300 66" preserveAspectRatio="none"></svg>
    <div class="info" id="dvTotal">—</div>

    <div class="kv" id="dvKv" style="margin-top:16px"></div>

    <div class="divider"></div>
    <div class="card-h"><h2>限速</h2><span class="ext" id="dvLimitNow">—</span></div>
    <div class="kv2">
      <div class="field" style="margin-bottom:6px">
        <label>下行上限</label>
        <div class="input-unit">
          <input type="number" inputmode="decimal" min="0" step="1" id="dvDownLimit" placeholder="0">
          <span>Mbps</span>
        </div>
      </div>
      <div class="field" style="margin-bottom:6px">
        <label>上行上限</label>
        <div class="input-unit">
          <input type="number" inputmode="decimal" min="0" step="1" id="dvUpLimit" placeholder="0">
          <span>Mbps</span>
        </div>
      </div>
    </div>
    <div class="chips" data-t="dvDownLimit">
      <button class="chip" data-v="10">下行 10</button>
      <button class="chip" data-v="50">50</button>
      <button class="chip" data-v="100">100</button>
      <button class="chip" data-v="0">不限</button>
    </div>
    <div class="chips" data-t="dvUpLimit">
      <button class="chip" data-v="2">上行 2</button>
      <button class="chip" data-v="5">5</button>
      <button class="chip" data-v="10">10</button>
      <button class="chip" data-v="0">不限</button>
    </div>
    <div class="note" id="dvNote" style="margin-top:12px">填 0 表示不限速；保存后对这台设备立即生效。</div>
    <div class="err" id="dvErr"></div>
    <div class="sheet-btns">
      <button class="btn2" id="dvClose">关闭</button>
      <button class="btn2 pri" id="dvSaveLimit">保存限速</button>
    </div>
  </div>
</div>

"""
a = h.index("<!-- 设备详情 / 限速 -->")
b = h.index('<div class="toast" id="toast"></div>')
h = h[:a] + DEV + h[b:]

# ---------------- 5. render() ----------------
a = h.index("function render(d) {")
b = h.index("let LAST = null;")
NEW_RENDER = r"""function avClass(mac) {
  let x = 0;
  const s = String(mac || '');
  for (let i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) >>> 0;
  return 'c' + (x % 6);
}

// ---------- 外网流量趋势（每次刷新采样一次，最多 60 个点 ≈ 10 分钟） ----------
const WAN_HIST = [];
function rateNum(s) {
  if (!s) return 0;
  const m = String(s).match(/([\d.]+)\s*([KMG]?)/i);
  if (!m) return 0;
  let v = parseFloat(m[1]) || 0;
  const u = (m[2] || '').toUpperCase();
  if (u === 'K') v /= 1000;
  else if (u === 'G') v *= 1000;
  return v;
}
function pushWan(down, up) {
  WAN_HIST.push([rateNum(down), rateNum(up)]);
  if (WAN_HIST.length > 60) WAN_HIST.shift();
  drawWanSpark();
}
function drawWanSpark() {
  const el = document.getElementById('wanSpark');
  if (!el) return;
  if (WAN_HIST.length < 2) { el.innerHTML = ''; return; }
  const W = 300, H = 42, PAD = 4;
  let max = 0.5;
  WAN_HIST.forEach((p) => { max = Math.max(max, p[0], p[1]); });
  const n = WAN_HIST.length;
  const step = W / (n - 1);
  const y = (v) => (H - PAD) - (v / max) * (H - PAD * 2);
  const line = (idx, stroke, fill) => {
    const pts = WAN_HIST.map((p, i) => (i * step).toFixed(1) + ',' + y(p[idx]).toFixed(1)).join(' ');
    let out = `<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>`;
    if (fill) out = `<polygon points="0,${H} ${pts} ${((n - 1) * step).toFixed(1)},${H}" fill="${fill}"/>` + out;
    return out;
  };
  el.innerHTML = line(1, 'rgba(255,255,255,.52)', '') + line(0, 'rgba(255,255,255,.95)', 'rgba(255,255,255,.14)');
}

function render(d) {
  LAST = d;
  $('#devName').textContent = d.dev.name;
  $('#devMeta').innerHTML = `<span class="dot"></span>${d.dev.model} · 固件 ${d.dev.fw}`;
  $('#foot').innerHTML = `<div class="foot-meta">${d.dev.model} · ${d.dev.mac}<br>${d.dev.ip} · ${d.count} 台设备在线</div><button class="linkbtn" id="btnOut">退出登录</button>`;
  $('#btnOut').onclick = async () => {
    await api('/api/logout', { method: 'POST' });
    sessionStorage.removeItem('zte_pwd');
    show('login');
  };

  const on = (d.wan.status || '').toLowerCase() === 'connected';
  const b = $('#wanBadge');
  b.className = 'badge' + (on ? '' : ' off');
  b.innerHTML = `<span class="dot" style="background:${on ? 'rgba(255,255,255,.94)' : 'rgba(255,255,255,.5)'}"></span>${on ? '已连接' : d.wan.status || '未连接'}`;
  $('#rateDown').innerHTML = fmtRate(d.wan.down);
  $('#rateUp').innerHTML = fmtRate(d.wan.up);
  pushWan(d.wan.down, d.wan.up);
  $('#wanIp').textContent = d.wan.ip || '—';
  $('#wanType').textContent = d.wan.type || '—';
  $('#wanUser').textContent = d.wan.user || '—';
  $('#wanUptime').textContent = d.wan.uptime;
  $('#wanSpeed').textContent = d.wan.speed ? d.wan.speed + ' Mbps' : '—';
  $('#lanIp').textContent = d.dev.ip;

  $('#wifiGrid').innerHTML = d.wifi.map((w) => `
    <div class="wifi ${w.on ? '' : 'off'}">
      <div class="wifi-top">
        <span class="band ${String(w.band).indexOf('5') === 0 ? 'b5' : 'b24'}">${w.band}</span>
        <span class="st">${w.on ? '已开启' : '已关闭'}</span>
      </div>
      <div class="ssid">${w.ssid || '未命名'}</div>
      <div class="info">${w.enc || '—'}${w.hidden ? ' · 隐藏' : ''}</div>
      <div class="info">最多 ${w.max || '—'} 台</div>
      <button class="edit" data-band="${w.band}">修改</button>
    </div>`).join('');
  $('#wifiGrid').querySelectorAll('.edit').forEach((eb) => {
    eb.onclick = () => openEdit(eb.dataset.band);
  });
  $('#wifiCount').textContent = `${d.wifi.filter((w) => w.on).length} 个开启 · 有线 ${d.wired} / 无线 ${d.wireless}`;

  $('#devCount').textContent = d.clients.length + ' 台';
  $('#runTime').textContent = d.dev.mesh ? 'Mesh 已开启' : '';
  $('#devList').innerHTML = d.clients.map((c) => {
    const nm = c.alias || c.name;
    const wireless = (c.iface || '').includes('802.11');
    const lim = LIMITS && LIMITS[String(c.mac || '').toUpperCase()];
    return `<div class="dev" data-mac="${c.mac}">
      <div class="av ${avClass(c.mac)}">${(nm || '?').trim().slice(0, 1).toUpperCase()}</div>
      <div class="dev-main">
        <div class="n">${nm}${lim ? ' <em class="limtag">限速</em>' : ''}</div>
        <div class="s"><span class="mtag">${wireless ? '无线' : '有线'}</span>${c.mac}</div>
      </div>
      <div class="dev-r">
        <div class="ip num">${c.ip}</div>
        <div class="t">${c.online}</div>
      </div>
      <div class="chev">›</div>
    </div>`;
  }).join('') || '<div class="empty">暂无在线设备</div>';
}

"""
h = h[:a] + NEW_RENDER + h[b:]

# ---------------- 6. openDev 里补头像 ----------------
old_open = """  $('#dvSub').textContent = DEV_MAC;"""
new_open = """  $('#dvSub').textContent = DEV_MAC;
  const av = $('#dvAv');
  av.className = 'av lg ' + avClass(DEV_MAC);
  av.textContent = String(c.alias || c.name || '?').trim().slice(0, 1).toUpperCase() || '?';"""
assert old_open in h
h = h.replace(old_open, new_open, 1)

# ---------------- 7. 限速预设按钮 + Esc 关弹层 ----------------
old_bind = "$('#devSheet').addEventListener('click', (e) => { if (e.target.id === 'devSheet') closeDev(); });"
new_bind = """$('#devSheet').addEventListener('click', (e) => { if (e.target.id === 'devSheet') closeDev(); });
// 限速预设：点一下就填进对应输入框，省得手机上敲数字
document.querySelectorAll('.chips').forEach((box) => {
  const target = document.getElementById(box.dataset.t);
  if (!target) return;
  box.querySelectorAll('.chip').forEach((c) => {
    c.onclick = () => { target.value = c.dataset.v; };
  });
});"""
assert old_bind in h
h = h.replace(old_bind, new_bind, 1)

old_esc = "document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeEdit(); });"
new_esc = "document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeEdit(); closeDev(); } });"
assert old_esc in h
h = h.replace(old_esc, new_esc, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(h)
print("ok, chars:", len(h))
