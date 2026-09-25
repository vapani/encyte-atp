// Fronts the ATP form container. Cloudflare Access sits in front of this
// Worker and decides who may reach it at all, so by the time a request arrives
// here it has already been authenticated.
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

export default {
  async fetch(request, env) {
    // One shared instance: three people, and no state worth keeping apart now
    // that engagement records go to the repository rather than to disk.
    return getContainer(env.ATP_CONTAINER, "shared").fetch(request);
  },
};
