// Supabase Edge Function: генерация OG-картинки 1200×630.
//
// Деплой (когда будет доступ):
//   supabase functions deploy generate-og --no-verify-jwt
//
// Пример:
//   /functions/v1/generate-og?title=Виленкин%206%20класс&subtitle=Номер%201.1&badge=Математика
//
// Функция отдаёт SVG: он лёгкий, кешируется CDN и не требует шрифтов в
// рантайме. Для площадок, которым обязателен PNG (Telegram, VK), используйте
// статические PNG из seo/og/ — их генерирует scripts/build_seo_pages.py.
// Для динамического PNG добавьте resvg-wasm и рендер SVG в PNG.

const WIDTH = 1200;
const HEIGHT = 630;

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, OPTIONS",
  "access-control-allow-headers": "content-type",
};

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function clamp(value: string | null, fallback: string, max: number): string {
  const text = (value ?? "").replace(/\s+/g, " ").trim() || fallback;
  return text.length > max ? text.slice(0, max - 1).trimEnd() + "…" : text;
}

function wrap(text: string, maxChars: number, maxLines: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length <= maxChars) {
      line = next;
    } else {
      if (line) lines.push(line);
      line = word;
      if (lines.length === maxLines - 1) break;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  return lines;
}

function renderSvg(title: string, subtitle: string, badge: string): string {
  const titleLines = wrap(title, 26, 3);
  const subtitleLines = wrap(subtitle, 52, 2);
  const titleSize = titleLines.length > 2 ? 64 : 74;
  const titleStart = 250;
  const titleTspans = titleLines
    .map((line, index) =>
      `<tspan x="88" dy="${index === 0 ? 0 : titleSize + 14}">${escapeXml(line)}</tspan>`
    )
    .join("");
  const subtitleTspans = subtitleLines
    .map((line, index) =>
      `<tspan x="88" dy="${index === 0 ? 0 : 42}">${escapeXml(line)}</tspan>`
    )
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}" role="img" aria-label="${escapeXml(title)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#063c3c"/>
      <stop offset="1" stop-color="#0d7c74"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#7ff0e0"/>
      <stop offset="1" stop-color="#25c2b3"/>
    </linearGradient>
  </defs>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="url(#bg)"/>
  <circle cx="1080" cy="80" r="210" fill="#25c2b3" opacity="0.12"/>
  <circle cx="1140" cy="560" r="180" fill="#7ff0e0" opacity="0.08"/>
  <rect x="56" y="56" width="${WIDTH - 112}" height="${HEIGHT - 112}" rx="36" fill="none" stroke="#ffffff" stroke-opacity="0.18" stroke-width="2"/>
  <text x="88" y="128" font-family="Arial, Helvetica, sans-serif" font-size="34" font-weight="700" fill="#7ff0e0">ГДЗ НЭЛ</text>
  <rect x="88" y="170" width="${Math.max(190, badge.length * 17 + 44)}" height="46" rx="23" fill="#25c2b3" opacity="0.18"/>
  <text x="${88 + Math.max(190, badge.length * 17 + 44) / 2}" y="201" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="700" fill="#bff8f0">${escapeXml(badge)}</text>
  <text x="88" y="${titleStart}" font-family="Arial, Helvetica, sans-serif" font-size="${titleSize}" font-weight="700" fill="#ffffff">${titleTspans}</text>
  <text x="88" y="${titleStart + titleLines.length * (titleSize + 14) + 44}" font-family="Arial, Helvetica, sans-serif" font-size="30" fill="#cfeeea">${subtitleTspans}</text>
  <rect x="88" y="520" width="190" height="6" rx="3" fill="url(#accent)"/>
  <text x="88" y="566" font-family="Arial, Helvetica, sans-serif" font-size="24" fill="#9fd8d2">gdz-nel.pages.dev · условия, решения и ответы</text>
</svg>`;
}

Deno.serve((request: Request) => {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }

  if (request.method !== "GET") {
    return new Response("method not allowed", {
      status: 405,
      headers: { ...CORS, allow: "GET, OPTIONS" },
    });
  }

  const url = new URL(request.url);
  const title = clamp(url.searchParams.get("title"), "ГДЗ НЭЛ", 90);
  const subtitle = clamp(
    url.searchParams.get("subtitle"),
    "Готовые решения и ответы для 1–11 классов",
    140,
  );
  const badge = clamp(url.searchParams.get("badge"), "1–11 класс", 30);

  return new Response(renderSvg(title, subtitle, badge), {
    status: 200,
    headers: {
      ...CORS,
      "content-type": "image/svg+xml; charset=utf-8",
      "cache-control": "public, max-age=86400, s-maxage=604800, stale-while-revalidate=86400",
      "x-content-type-options": "nosniff",
    },
  });
});
