function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(value: string) {
  let text = escapeHtml(value);
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
    const raw = href.replace(/&amp;/g, "&");
    const safe = raw.startsWith("/") || raw.startsWith("https://") || raw.startsWith("http://") ? raw : "#";
    return `<a href="${escapeHtml(safe)}" class="underline">${label}</a>`;
  });
  return text;
}

function isTableRow(line: string) {
  return line.trim().startsWith("|");
}

function tableCells(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isSeparator(line: string) {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim());
}

export function renderMarkdown(source: string) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level} class="font-semibold text-slate-900 mt-6 mb-2">${inline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }
    if (isTableRow(line)) {
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) {
        if (!isSeparator(lines[i])) rows.push(tableCells(lines[i]));
        i += 1;
      }
      const head = rows[0] ?? [];
      const body = rows.slice(1);
      html.push('<div class="overflow-x-auto my-4"><table class="w-full text-sm border-collapse">');
      html.push("<thead><tr>" + head.map((cell) => `<th class="border border-slate-200 px-2 py-1 text-left">${inline(cell)}</th>`).join("") + "</tr></thead>");
      html.push("<tbody>");
      for (const row of body) {
        html.push("<tr>" + row.map((cell) => `<td class="border border-slate-200 px-2 py-1 align-top">${inline(cell)}</td>`).join("") + "</tr>");
      }
      html.push("</tbody></table></div>");
      continue;
    }
    if (line.trim().startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("- ")) {
        items.push(lines[i].trim().slice(2));
        i += 1;
      }
      html.push("<ul class=\"list-disc pl-5 my-3 space-y-1\">" + items.map((item) => `<li>${inline(item)}</li>`).join("") + "</ul>");
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !isTableRow(lines[i]) && !lines[i].trim().startsWith("- ")) {
      para.push(lines[i].trim());
      i += 1;
    }
    html.push(`<p class="my-3 leading-relaxed">${inline(para.join(" "))}</p>`);
  }
  return html.join("\n");
}
