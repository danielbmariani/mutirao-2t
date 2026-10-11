// Auditoria do site eleitores: escopo Brasil/UF/município com VOO do
// mapa, avisos, sheet de 3 alturas no mobile. Uso: node bateria [url]
const puppeteer = require("puppeteer-core");
const URL = process.argv[2] || "http://localhost:8772/index.html";
const falhas = [];
const ok = (cond, nome) => {
  console.log((cond ? "PASS" : "FAIL") + " " + nome);
  if (!cond) falhas.push(nome);
};
(async () => {
  const b = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome",
    headless: "new", args: ["--no-sandbox", "--window-size=1400,900"] });
  // ---------- desktop ----------
  const p = await b.newPage();
  await p.setViewport({ width: 1400, height: 900 });
  const erros = [];
  p.on("pageerror", e => erros.push(e.message));
  await p.goto(URL, { waitUntil: "networkidle2", timeout: 90000 });
  await new Promise(r => setTimeout(r, 8000));
  ok(await p.evaluate(() =>
    document.querySelectorAll("#pr-lista .reg").length === 50),
    "Brasil: top 50");
  const c0 = await p.evaluate(() => mapa.getCenter().lng);
  // escopo UF via BOTÃO (toque, sem digitar)
  await p.evaluate(() => document.getElementById("esc-uf").click());
  await new Promise(r => setTimeout(r, 300));
  await p.evaluate(() =>
    [...document.querySelectorAll("#escopo-sug .sug")]
      .find(x => x.textContent.includes("(GO)"))
      .dispatchEvent(new Event("mousedown")));
  await new Promise(r => setTimeout(r, 1800));
  ok(await p.evaluate(() =>
    document.querySelectorAll("#pr-lista .reg").length === 25),
    "GO: top 25");
  ok(await p.evaluate(() => {
    const c = mapa.getCenter();
    return c.lng > -54 && c.lng < -45 && c.lat > -20 && c.lat < -12;
  }), "GO: mapa voou para o estado");
  ok(await p.evaluate(() =>
    document.getElementById("esc-uf").textContent.includes("GO")),
    "GO: rótulo do botão");
  // UF sem região (SE) via botão
  await p.evaluate(() => document.getElementById("esc-uf").click());
  await new Promise(r => setTimeout(r, 300));
  await p.evaluate(() =>
    [...document.querySelectorAll("#escopo-sug .sug")]
      .find(x => x.textContent.includes("(SE)"))
      .dispatchEvent(new Event("mousedown")));
  await new Promise(r => setTimeout(r, 1500));
  ok(await p.evaluate(() =>
    (document.querySelector(".pr-aviso") || {}).textContent
      ?.includes("Nenhuma região")), "SE: aviso de UF vazia");
  // município com região: botão + sugestões por TOQUE (UF ativa = SE,
  // então digita goiania p/ sair da UF)
  await p.evaluate(() => document.getElementById("esc-mu").click());
  await new Promise(r => setTimeout(r, 300));
  await p.evaluate(() => {
    const i = document.getElementById("escopo-busca");
    i.value = "goiania"; i.dispatchEvent(new Event("input"));
  });
  await new Promise(r => setTimeout(r, 400));
  await p.evaluate(() => document.querySelector("#escopo-sug .sug")
    .dispatchEvent(new Event("mousedown")));
  await new Promise(r => setTimeout(r, 2200));
  const stGyn = await p.evaluate(() => ({
    n: document.querySelectorAll("#pr-lista .reg").length,
    zoom: mapa.getZoom(),
    lng: mapa.getCenter().lng,
    bc: document.getElementById("esc-mu").textContent }));
  ok(stGyn.n >= 1 && stGyn.n <= 10, "Goiânia: até 10 regiões");
  ok(stGyn.zoom > 9 && Math.abs(stGyn.lng + 49.26) < 0.5,
     "Goiânia: mapa voou para o município");
  ok(stGyn.bc.includes("Goiânia"), "Goiânia: rótulo do botão");
  // voltar ao Brasil pelo botão
  await p.evaluate(() => document.getElementById("esc-br").click());
  await new Promise(r => setTimeout(r, 1500));
  ok(await p.evaluate(() =>
    document.querySelectorAll("#pr-lista .reg").length === 50),
    "botão Brasil: volta ao top 50");
  // município SEM região
  await p.evaluate(() => document.getElementById("esc-mu").click());
  await new Promise(r => setTimeout(r, 300));
  await p.evaluate(() => {
    const i = document.getElementById("escopo-busca");
    i.value = "aracaju"; i.dispatchEvent(new Event("input"));
  });
  await new Promise(r => setTimeout(r, 400));
  await p.evaluate(() => document.querySelector("#escopo-sug .sug")
    .dispatchEvent(new Event("mousedown")));
  await new Promise(r => setTimeout(r, 1800));
  ok(await p.evaluate(() =>
    (document.querySelector(".pr-aviso") || {}).textContent
      ?.includes("Nada em")), "Aracaju: aviso de município sem região");
  // corte do modelo: Mais regiões
  await p.evaluate(() => document.getElementById("esc-br").click());
  await new Promise(r => setTimeout(r, 800));
  await p.evaluate(() => document.getElementById("corte-mais").click());
  await new Promise(r => setTimeout(r, 2500));
  const stMais = await p.evaluate(() => ({
    meta: REG.meta.n_regioes,
    fontes: mapa.getSource("regioes")._data.features.length }));
  ok(stMais.meta > 300 && stMais.fontes === stMais.meta,
     "corte Mais: conjunto trocado no painel e no mapa (" +
     stMais.meta + ")");
  // mostrar todas
  await p.evaluate(() => document.querySelector(".pr-mais").click());
  await new Promise(r => setTimeout(r, 600));
  ok(await p.evaluate(() =>
    document.querySelectorAll("#pr-lista .reg").length > 300),
    "Mostrar todas: lista expandida");
  await p.evaluate(() => document.getElementById("corte-padrao").click());
  await new Promise(r => setTimeout(r, 2000));
  ok(await p.evaluate(() =>
    document.querySelectorAll("#pr-lista .reg").length === 50),
    "corte Padrão: volta ao top 50");
  ok(erros.length === 0, "desktop sem pageerrors (" + erros.length + ")");
  // ---------- visão ABSTENÇÃO ----------
  await p.evaluate(() => document.getElementById("esc-br").click());
  await new Promise(r => setTimeout(r, 600));
  await p.evaluate(() => document.getElementById("visao-abst").click());
  await new Promise(r => setTimeout(r, 2500));
  ok(await p.evaluate(() => REG.meta.n_regioes > 40 &&
     REG.meta.n_regioes < 120), "abst: conjunto próprio carregado");
  ok(await p.evaluate(() =>
    document.getElementById("cand-resumo").textContent
      .includes("abstenção")), "abst: resumo adaptado");
  ok(await p.evaluate(() => JSON.stringify(
    mapa.getPaintProperty("municipios-fill", "fill-color"))
      .includes('"a"')), "abst: mapa pinta pelo atributo a");
  await p.evaluate(() =>
    document.querySelector("#pr-lista .reg").click());
  await new Promise(r => setTimeout(r, 2200));
  const fichaAbst = await p.evaluate(() =>
    document.getElementById("resultado").textContent);
  ok(fichaAbst.includes("Abstenção") &&
     fichaAbst.includes("Ganho líquido"),
     "abst: ficha com abstenção e ganho líquido");
  await p.evaluate(() => document.getElementById("visao-voto").click());
  await new Promise(r => setTimeout(r, 2200));
  ok(await p.evaluate(() => REG.meta.n_regioes === 132),
     "volta à visão voto (132)");
  // carga inicial com hash de corte (regressão TDZ 11/10)
  const p2 = await b.newPage();
  const erros2 = [];
  p2.on("pageerror", e => erros2.push(e.message.slice(0,80)));
  await p2.goto(URL.replace(/#.*/, "") + "#v=abst&s=mais",
                { waitUntil: "networkidle2", timeout: 90000 });
  await new Promise(r => setTimeout(r, 7000));
  ok(await p2.evaluate(() => REG && REG.meta.n_regioes > 120 &&
     REG.meta.n_regioes < 220),
     "hash v=abst&s=mais: conjunto certo na abertura");
  ok(erros2.length === 0,
     "hash: sem pageerrors (" + erros2.join(";") + ")");
  await p2.close();
  await p.screenshot({ path: "/tmp/eleitores_aud_desktop.png" });
  await p.close();
  // ---------- mobile: sheet de 3 alturas ----------
  const m = await b.newPage();
  await m.setViewport({ width: 390, height: 844, isMobile: true,
                        hasTouch: true });
  const errosM = [];
  m.on("pageerror", e => errosM.push(e.message));
  await m.goto(URL, { waitUntil: "networkidle2", timeout: 90000 });
  await new Promise(r => setTimeout(r, 8000));
  const cls = sel => m.evaluate(s =>
    document.getElementById("painel-regioes").className, sel);
  ok((await cls()).includes("meia"), "mobile: abre na altura MEIA");
  const hMeia = await m.evaluate(() =>
    document.getElementById("painel-regioes").offsetHeight);
  ok(hMeia < 844 * 0.55, "mobile: meia altura deixa o mapa visível");
  await m.evaluate(() => document.getElementById("pr-handle").click());
  await new Promise(r => setTimeout(r, 400));
  ok((await cls()).includes("cheia"), "mobile: alça expande p/ CHEIA");
  // focar região recolhe ao pico
  await m.evaluate(() =>
    document.querySelector("#pr-lista .reg").click());
  await new Promise(r => setTimeout(r, 2000));
  ok((await cls()).includes("peek"), "mobile: focar região -> PICO");
  const hPeek = await m.evaluate(() =>
    document.getElementById("painel-regioes").offsetHeight);
  ok(hPeek < 120, "mobile: pico compacto (" + hPeek + "px)");
  // regressão 11/10: esfera com sheet no PICO deve levantar p/ MEIA
  await m.evaluate(() => setDetente("peek"));
  await new Promise(r => setTimeout(r, 400));
  await m.evaluate(() => document.getElementById("esc-uf").click());
  await new Promise(r => setTimeout(r, 500));
  ok((await cls()).includes("meia"),
     "mobile: esfera no pico levanta o sheet");
  ok(await m.evaluate(() =>
    document.getElementById("escopo-sug").classList.contains("aberto")),
    "mobile: lista de estados visível");
  await m.evaluate(() =>
    [...document.querySelectorAll("#escopo-sug .sug")]
      .find(x => x.textContent.includes("(BA)"))
      .dispatchEvent(new Event("mousedown")));
  await new Promise(r => setTimeout(r, 1500));
  ok(await m.evaluate(() =>
    document.querySelectorAll("#pr-lista .reg").length > 0),
    "mobile: BA listada após seleção");
  ok(errosM.length === 0, "mobile sem pageerrors (" + errosM.length + ")");
  await m.screenshot({ path: "/tmp/eleitores_aud_mobile.png" });
  await b.close();
  console.log(falhas.length ? "FALHAS: " + falhas.join("; ")
                            : "AUDITORIA APROVADA");
  process.exit(falhas.length ? 1 : 0);
})();
