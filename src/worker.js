export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/ping") {
      return new Response(
        JSON.stringify({
          ok: true,
          service: "hara-site",
          message: "Worker ativo"
        }),
        {
          headers: {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store"
          }
        }
      );
    }

    return env.ASSETS.fetch(request);
  }
};
