// Execute: node docs/screenshots/capture.cjs [arquivo.png]
// Usa apenas dependências já instaladas no frontend e Chrome/Edge local.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn } = require("node:child_process");

const root = path.resolve(__dirname, "../..");
const frontend = path.join(root, "frontend");
const htmlPath = path.join(frontend, ".capture-documentation.html");
const entryPath = path.join(frontend, ".capture-documentation.jsx");
const port = 5175;
const debuggingPort = 9229;
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function until(check, label, timeout = 30000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    try {
      const result = await check();
      if (result) return result;
    } catch {}
    await delay(150);
  }
  throw new Error(`Tempo esgotado: ${label}`);
}

async function main() {
  if (fs.existsSync(htmlPath) || fs.existsSync(entryPath)) throw new Error("Uma entrada temporária de captura já existe; confira antes de substituir.");
  const executable = process.env.AGRISHIELD_CAPTURE_BROWSER || [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
  ].find((candidate) => fs.existsSync(candidate));
  if (!executable) throw new Error("Defina AGRISHIELD_CAPTURE_BROWSER com o caminho do Chrome/Edge.");
  const vitePath = path.join(frontend, "node_modules/vite/bin/vite.js");
  if (!fs.existsSync(vitePath)) throw new Error("Instale primeiro as dependências do frontend com npm ci.");

  let vite;
  let browser;
  let ws;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "agrishield-capture-"));
  try {
    fs.copyFileSync(path.join(__dirname, "capture-entry.jsx"), entryPath);
    fs.writeFileSync(htmlPath, '<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>AgriShield · documentação</title></head><body><div id="root"></div><script type="module" src="/.capture-documentation.jsx"></script></body></html>');
    vite = spawn(process.execPath, [vitePath, "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
      cwd: frontend, windowsHide: true, stdio: "pipe",
      env: { ...process.env, VITE_API_URL: `http://127.0.0.1:${port}`, VITE_SUPABASE_URL: "", VITE_SUPABASE_PUBLISHABLE_KEY: "", VITE_SUPABASE_ANON_KEY: "" },
    });
    let viteLog = "";
    vite.stdout.on("data", (chunk) => { viteLog = (viteLog + chunk).slice(-12000); });
    vite.stderr.on("data", (chunk) => { viteLog = (viteLog + chunk).slice(-12000); });
    await until(async () => (await fetch(`http://127.0.0.1:${port}/.capture-documentation.html`)).ok, "Vite local").catch((error) => { throw new Error(`${error.message}\n${viteLog}`); });
    if (vite.exitCode !== null) throw new Error(`Vite encerrou: ${viteLog}`);
    browser = spawn(executable, ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-background-networking", `--remote-debugging-port=${debuggingPort}`, `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
    const version = await until(async () => (await fetch(`http://127.0.0.1:${debuggingPort}/json/version`)).json(), "navegador Chromium");
    ws = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.addEventListener("open", resolve, { once: true }); ws.addEventListener("error", reject, { once: true }); });
    let id = 0;
    const pending = new Map();
    let exceptions = [];
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const request = pending.get(message.id);
        if (request) {
          pending.delete(message.id);
          if (message.error) request.reject(new Error(JSON.stringify(message.error)));
          else request.resolve(message.result);
        }
      } else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text + ": " + (message.params.exceptionDetails.exception?.description || ""));
    });
    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
      const nextId = ++id;
      pending.set(nextId, { resolve, reject });
      ws.send(JSON.stringify({ id: nextId, method, params, ...(sessionId && { sessionId }) }));
    });
    const target = await send("Target.createTarget", { url: "about:blank" });
    const attached = await send("Target.attachToTarget", { targetId: target.targetId, flatten: true });
    const session = attached.sessionId;
    const command = (method, params) => send(method, params, session);
    await command("Page.enable");
    await command("Runtime.enable");
    const captures = [
      ["01-visao-geral.png", "dashboard"],
      ["02-clientes-apolices.png", "clientes"],
      ["03-maquinarios.png", "maquinarios"],
      ["04-cadastro-fazenda.png", "cadastro"],
      ["05-riscos-score.png", "riscos"],
      ["06-insights.png", "insights"],
      ["07-insights-briefing.png", "insights", "briefing"],
      ["08-insights-mobile.png", "insights", "", true],
      ["09-operacoes-territorio.png", "operacoes"],
      ["10-exposicao-maquinario.png", "exposicao"],
      ["11-login.png", "login"],
    ];
    const requested = process.argv[2];
    const selectedCaptures = requested ? captures.filter(([filename]) => filename === requested) : captures;
    if (!selectedCaptures.length) throw new Error(`Captura desconhecida: ${requested}`);
    for (const [filename, page, scroll = "", mobile = false] of selectedCaptures) {
      exceptions = [];
      await command("Emulation.setDeviceMetricsOverride", { width: mobile ? 390 : 1512, height: mobile ? 844 : 1080, deviceScaleFactor: 1, mobile });
      await command("Page.navigate", { url: `http://127.0.0.1:${port}/.capture-documentation.html?page=${page}&scroll=${scroll}` });
      await until(async () => (await command("Runtime.evaluate", { expression: 'document.documentElement.dataset.captureReady === "true"', returnByValue: true })).result?.value, `render de ${filename}`);
      if (exceptions.length) throw new Error(`${filename}: ${exceptions.join("\n")}`);
      const text = (await command("Runtime.evaluate", { expression: "document.body.innerText", returnByValue: true })).result.value;
      if (!text.includes("DOCUMENTAÇÃO") || text.length < 200) throw new Error(`Página incompleta: ${filename}`);
      const screenshot = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
      fs.writeFileSync(path.join(__dirname, filename), Buffer.from(screenshot.data, "base64"));
      console.log(`Capturado: ${filename}`);
    }
    for (const [source, destination] of [
      ["01-visao-geral.png", "docs/docs_dashboard.png"],
      ["02-clientes-apolices.png", "docs/docs_clientes.png"],
      ["04-cadastro-fazenda.png", "docs/docs_cadastro.png"],
      ["08-insights-mobile.png", "output/insights-production-mobile.png"],
    ]) fs.copyFileSync(path.join(__dirname, source), path.join(root, destination));
    await send("Browser.close");
    console.log(`${selectedCaptures.length} capturas concluídas e 4 cópias sincronizadas. A API da aplicação e a LLM foram simuladas.`);
  } finally {
    ws?.close();
    if (browser?.exitCode === null) browser.kill();
    if (vite?.exitCode === null) vite.kill();
    for (const temporary of [htmlPath, entryPath]) if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
    await delay(500);
    // Apenas o perfil temporário criado por esta execução.
    if (profile.startsWith(path.join(os.tmpdir(), "agrishield-capture-"))) {
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
    }
  }
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; });
