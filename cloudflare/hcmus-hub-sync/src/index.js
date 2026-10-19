const SCHEMA_VERSION = 1;
const MANIFEST_KEY = "manifest.json";
const SNAPSHOT_PREFIX = "snapshots/";
const MAX_REQUEST_BYTES = 64 * 1024 * 1024;
const MAX_SNAPSHOT_BYTES = 60 * 1024 * 1024;
const MAX_MANIFEST_BYTES = 1024 * 1024;
const ALLOWED_ORIGINS = new Set([
  "http://127.0.0.1:8787",
  "http://localhost:8787",
]);

function corsHeaders(request) {
  const origin = request.headers.get("Origin");
  const headers = { "Vary": "Origin" };
  if (origin && ALLOWED_ORIGINS.has(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
    headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, If-Match, If-None-Match";
  }
  return headers;
}

function jsonResponse(request, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders(request),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function errorResponse(request, status, message) {
  return jsonResponse(request, { error: message }, status);
}

function hex(buffer) {
  return [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256(bytes) {
  return hex(await crypto.subtle.digest("SHA-256", bytes));
}

function validRecordCounts(records) {
  return records && Number.isInteger(records.sources) &&
    Number.isInteger(records.articles) && Number.isInteger(records.links) &&
    records.sources >= 0 && records.articles >= 0 && records.links >= 0;
}

function validateManifest(manifest) {
  if (!manifest || manifest.schema_version !== SCHEMA_VERSION ||
      !manifest.snapshot || typeof manifest.snapshot !== "object" ||
      typeof manifest.snapshot.filename !== "string" ||
      manifest.snapshot.filename.length < 1 ||
      !/^[0-9a-f]{64}$/i.test(manifest.snapshot.sha256) ||
      !Number.isInteger(manifest.snapshot.size) || manifest.snapshot.size < 1 ||
      !validRecordCounts(manifest.records)) {
    throw new Error("Manifest không đúng schema snapshot.");
  }
}

async function validateSnapshotJson(bytes, manifest) {
  if (bytes.length < 2 || bytes[0] !== 0x1f || bytes[1] !== 0x8b) {
    throw new Error("Snapshot không phải gzip.");
  }
  const stream = new Response(bytes).body.pipeThrough(new DecompressionStream("gzip"));
  const payload = JSON.parse(await new Response(stream).text());
  if (!payload || payload.schema_version !== SCHEMA_VERSION ||
      !Array.isArray(payload.sources) || !Array.isArray(payload.articles) ||
      !Number.isInteger(payload.data_revision) || payload.data_revision < 0 ||
      payload.sources.length !== manifest.records.sources ||
      payload.articles.length !== manifest.records.articles ||
      !payload.articles.every((article) =>
        article && typeof article === "object" && Array.isArray(article.links)) ||
      payload.articles.reduce((total, article) => total + article.links.length, 0) !==
        manifest.records.links) {
    throw new Error("Nội dung snapshot không đúng schema hoặc manifest.");
  }
}

async function readManifest(env) {
  const object = await env.HUB_BUCKET.get(MANIFEST_KEY);
  if (!object) throw new Error("Chưa có manifest.");
  const manifest = await object.json();
  validateManifest(manifest);
  return manifest;
}

async function readManifestObject(env) {
  const object = await env.HUB_BUCKET.get(MANIFEST_KEY);
  if (!object) throw new Error("Chưa có manifest.");
  const manifest = await object.json();
  validateManifest(manifest);
  return { manifest, etag: object.httpEtag };
}

function authorized(request, env) {
  const value = request.headers.get("Authorization") || "";
  return value.startsWith("Bearer ") &&
    value.slice("Bearer ".length) === env.HUB_WRITE_TOKEN;
}

async function publish(request, env) {
  const length = Number(request.headers.get("Content-Length") || 0);
  if (length > MAX_REQUEST_BYTES) {
    return errorResponse(request, 413, "Request vượt giới hạn kích thước.");
  }
  let form;
  try {
    form = await request.formData();
  } catch (_) {
    return errorResponse(request, 400, "Multipart không hợp lệ.");
  }
  const snapshot = form.get("snapshot");
  const manifestPart = form.get("manifest");
  if (!(snapshot instanceof File) || !(manifestPart instanceof File)) {
    return errorResponse(request, 400, "Multipart cần file snapshot và manifest.");
  }
  if (snapshot.size > MAX_SNAPSHOT_BYTES || manifestPart.size > MAX_MANIFEST_BYTES) {
    return errorResponse(request, 413, "File vượt giới hạn kích thước.");
  }
  let manifest;
  try {
    manifest = JSON.parse(await manifestPart.text());
    validateManifest(manifest);
  } catch (_) {
    return errorResponse(request, 400, "Manifest JSON không hợp lệ.");
  }
  const bytes = new Uint8Array(await snapshot.arrayBuffer());
  const digest = await sha256(bytes);
  if (digest !== manifest.snapshot.sha256.toLowerCase() ||
      bytes.length !== manifest.snapshot.size) {
    return errorResponse(request, 400, "SHA-256 hoặc kích thước snapshot không khớp manifest.");
  }
  try {
    await validateSnapshotJson(bytes, manifest);
  } catch (_) {
    return errorResponse(request, 400, "Snapshot gzip/JSON không hợp lệ.");
  }
  const key = `${SNAPSHOT_PREFIX}${digest}.json.gz`;
  await env.HUB_BUCKET.put(key, bytes, {
    httpMetadata: { contentType: "application/gzip" },
  });
  const storedManifest = {
    ...manifest,
    snapshot: { ...manifest.snapshot, filename: `${digest}.json.gz` },
  };
  const written = await env.HUB_BUCKET.put(MANIFEST_KEY, JSON.stringify(storedManifest), {
    onlyIf: request.headers,
    httpMetadata: { contentType: "application/json; charset=utf-8" },
  });
  if (!written) return errorResponse(request, 409, "Manifest đã thay đổi; cần pull và merge lại.");
  return jsonResponse(request, { ok: true, manifest: storedManifest });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }
    if (url.pathname === "/api/health" && request.method === "GET") {
      return jsonResponse(request, { status: "ok" });
    }
    if (url.pathname === "/api/manifest" && request.method === "GET") {
      try {
        const result = await readManifestObject(env);
        const response = jsonResponse(request, result.manifest);
        response.headers.set("ETag", result.etag);
        return response;
      } catch (error) {
        return errorResponse(request, 404, error.message);
      }
    }
    if (url.pathname === "/api/snapshot" && request.method === "GET") {
      try {
        const manifest = await readManifest(env);
        const object = await env.HUB_BUCKET.get(`${SNAPSHOT_PREFIX}${manifest.snapshot.sha256}.json.gz`);
        if (!object) return errorResponse(request, 404, "Không tìm thấy snapshot.");
        return new Response(object.body, {
          headers: {
            ...corsHeaders(request),
            "Content-Type": "application/gzip",
            "Content-Length": String(manifest.snapshot.size),
            "Cache-Control": "no-store",
          },
        });
      } catch (error) {
        return errorResponse(request, 404, error.message);
      }
    }
    if (url.pathname === "/api/publish" && request.method === "POST") {
      if (!authorized(request, env)) return errorResponse(request, 401, "Không được phép.");
      return publish(request, env);
    }
    return errorResponse(request, 404, "Không tìm thấy.");
  },
};
