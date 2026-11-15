import {readFile, writeFile, mkdir, copyFile} from "node:fs/promises";
const read = file => readFile(new URL(file, import.meta.url), "utf8");
const [css, js] = await Promise.all([read("web/style.css"), read("web/app.js")]);
const html = (await read("web/index.html")).replace("/* STYLE */", () => css).replace("/* SCRIPT */", () => js);
await mkdir("dist/server", {recursive:true});
await mkdir("dist/.openai", {recursive:true});
await writeFile("dist/server/index.js", "const PAGE = " + JSON.stringify(html) + ";\n" + await read("service/site.mjs"));
await copyFile(".openai/hosting.json", "dist/.openai/hosting.json");
