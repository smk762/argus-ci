// Writes out/: a two-page static site in the shape of a trailingSlash export. With --broken the
// home page logs a console error on load, which the default noConsoleErrors property must catch.
import { mkdirSync, rmSync, writeFileSync } from "node:fs";

const broken = process.argv.includes("--broken");
const page = (title, body) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${title}</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="/app.css">
</head>
<body>
<main>
<h1>${title}</h1>
${body}
</main>
</body>
</html>
`;

rmSync("out", { recursive: true, force: true });
mkdirSync("out/about", { recursive: true });
writeFileSync("out/app.css", "body { font-family: sans-serif; max-width: 40rem; margin: 2rem auto; }\n");
writeFileSync(
  "out/index.html",
  page(
    "Home",
    `<p><a href="/about/">About</a> · <a href="/about">About, no slash</a></p>
<label>Name <input name="name"></label>
<button type="button" onclick="this.textContent = 'Pressed'">Press</button>` +
      (broken ? `\n<script>console.error("bombadil-fixture: a deliberate console error");</script>` : ""),
  ),
);
writeFileSync("out/about/index.html", page("About", `<p><a href="/">Home</a></p>`));
console.log(`wrote out/ (${broken ? "broken" : "ok"})`);
