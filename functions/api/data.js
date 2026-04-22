export async function onRequest(context) {
  // 替换为你的新仓库地址
  const GITHUB_RAW = 'https://raw.githubusercontent.com/daowei88/daoid/main/apple_ids.json';

  try {
    const resp = await fetch(GITHUB_RAW, {
      cf: { cacheEverything: false },
    });

    if (!resp.ok) {
      return new Response(JSON.stringify({ error: 'fetch failed: ' + resp.status }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const text = await resp.text();

    return new Response(text, {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'no-store, max-age=0',
      },
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
