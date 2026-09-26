// Fronts the ATP form container.
//
// Access control lives here rather than in Cloudflare Access, because Access
// needs a hostname on a zone in the account and this is served from
// workers.dev. A password is weaker than single sign-on: it is shared, it does
// not say who issued a contract, and it cannot be revoked for one person. If a
// domain is ever added to this Cloudflare account, replace this with Access.
import { Container, getContainer } from "@cloudflare/containers";

export class AtpContainer extends Container {
  defaultPort = 8080;      // serve.py listens here, via ATP_PORT
  sleepAfter = "20m";      // idle instances stop; the next request wakes one

  constructor(ctx, env) {
    super(ctx, env);
    // Secrets have to be read here and handed to the container process - a
    // static envVars block cannot see them, and without the token the
    // engagement record silently never saves.
    this.envVars = {
      ATP_HOST: "0.0.0.0",
      ATP_PORT: "8080",
      ATP_OPEN_BROWSER: "0",
      ATP_GITHUB_TOKEN: env.ATP_GITHUB_TOKEN ?? "",
      ATP_GITHUB_REPO: env.ATP_GITHUB_REPO ?? "vapani/encyte-atp",
      ATP_GITHUB_BRANCH: env.ATP_GITHUB_BRANCH ?? "main",
    };
  }
}

const UNAUTHORISED = () =>
  new Response("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Encyte ATP", charset="UTF-8"' },
  });

// Compare without leaking how much of the password matched.
function same(a, b) {
  const x = new TextEncoder().encode(a);
  const y = new TextEncoder().encode(b);
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const expected = env.ATP_PASSWORD;

    // Refuse to serve at all rather than fall open if the secret is missing.
    if (!expected) {
      return new Response(
        "This deployment has no ATP_PASSWORD set, so it is refusing to serve.\n" +
          "Set one with:  npx wrangler secret put ATP_PASSWORD\n",
        { status: 503, headers: { "Content-Type": "text/plain" } },
      );
    }

    const header = request.headers.get("Authorization") || "";
    if (!header.startsWith("Basic ")) return UNAUTHORISED();
    let decoded;
    try {
      decoded = atob(header.slice(6));
    } catch {
      return UNAUTHORISED();
    }
    const password = decoded.slice(decoded.indexOf(":") + 1);
    if (!same(password, expected)) return UNAUTHORISED();

    // One shared instance: three people, and no state worth keeping apart now
    // that engagement records go to the repository rather than to disk.
    return getContainer(env.ATP_CONTAINER, "shared").fetch(request);
  },
};
