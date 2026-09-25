import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  expect,
  request as playwrightRequest,
  test as base,
  type APIRequestContext,
  type APIResponse,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
  type Page,
  type TestInfo,
} from "@playwright/test";
import { API_URL, USERS, type Role } from "./env";

export { API_URL, EVENT_SLUG, USERS, type Role } from "./env";

/*
 * Sessions
 * ────────
 * POST /auth/login allows 10 attempts per minute and IP, /auth/refresh 30.
 * A full suite needs far more sessions than that, so each role signs in once
 * and the session is handed from test to test: the app keeps its access token
 * in memory and restores it on every page load from the (rotating) refresh
 * cookie. After a test the context's newest cookie is stored under
 * e2e/.auth/<role>.json and the next test of that role continues the chain.
 * Only when the chain is broken (fresh database, logout) does a role sign in
 * again. The suite runs with one worker, so the chains never fork. Should a
 * login or a session restore still hit the limit, the helpers wait out its
 * Retry-After instead of failing.
 */

const AUTH_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), ".auth");
const cookieFile = (key: string) => path.join(AUTH_DIR, `${key}.json`);

type Cookies = Awaited<ReturnType<BrowserContext["cookies"]>>;

function readCookies(key: string): Cookies {
  try {
    return JSON.parse(fs.readFileSync(cookieFile(key), "utf8")) as Cookies;
  } catch {
    return [];
  }
}

function writeCookies(key: string, cookies: Cookies) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  fs.writeFileSync(cookieFile(key), JSON.stringify(cookies));
}

function forgetCookies(key: string) {
  fs.rmSync(cookieFile(key), { force: true });
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Sit out a 429 for as long as its Retry-After says, extending the test's timeout. */
async function waitOutRateLimit(headers: Record<string, string>) {
  const wait = Number(headers["retry-after"] ?? "10") + 1;
  base.info().setTimeout(base.info().timeout + wait * 1000);
  await sleep(wait * 1000);
}

/** POST to an auth endpoint, waiting out the rate limit instead of failing. */
async function postWithRateLimit(context: APIRequestContext, url: string, data: object): Promise<APIResponse> {
  for (let attempt = 0; ; attempt++) {
    const response = await context.post(url, { data });
    if (response.status() !== 429 || attempt >= 3) return response;
    await waitOutRateLimit(response.headers());
  }
}

/** Sign `role` in through the API; the refresh cookie lands in `context`. */
async function apiLogin(context: APIRequestContext, role: Role): Promise<string> {
  const response = await postWithRateLimit(context, `${API_URL}/auth/login`, USERS[role]);
  expect(response.status(), `login as ${role}`).toBe(200);
  return (await response.json()).access_token as string;
}

/** Options of the current project (device, baseURL) for extra contexts. */
function projectContextOptions(testInfo: TestInfo): BrowserContextOptions {
  const use = testInfo.project.use as BrowserContextOptions;
  const keys = ["baseURL", "viewport", "userAgent", "deviceScaleFactor", "isMobile", "hasTouch", "locale", "timezoneId"] as const;
  return Object.fromEntries(keys.filter((key) => use[key] !== undefined).map((key) => [key, use[key]]));
}

/**
 * Load `url`, which makes the app restore its session from the refresh
 * cookie. Resolves whether that worked; a rate-limited restore (which leaves
 * the cookie untouched) is waited out and repeated.
 */
async function loadWithSession(page: Page, url: string): Promise<boolean> {
  for (let attempt = 0; attempt < 4; attempt++) {
    const restore = page.waitForResponse(
      (response) => response.url() === `${API_URL}/auth/refresh` && response.request().method() === "POST",
    );
    await page.goto(url);
    const response = await restore;
    if (response.status() !== 429) return response.ok();
    await waitOutRateLimit(response.headers());
  }
  throw new Error("session restore stayed rate limited");
}

/**
 * Reload the app at `url` (default: where it is), e.g. to see what another
 * user changed meanwhile - the app caches API data for 30 s.
 */
export async function reloadApp(page: Page, url = page.url()) {
  expect(await loadWithSession(page, url), "session restored after reload").toBe(true);
}

/**
 * Open the app as `role` in `page` and wait until it shows an event.
 * Resumes the role's stored session, or signs in.
 */
async function openApp(page: Page, role: Role) {
  const context = page.context();
  const cookies = readCookies(role);
  if (cookies.length) await context.addCookies(cookies);
  else await apiLogin(context.request, role);
  for (let attempt = 0; attempt < 2; attempt++) {
    if (await loadWithSession(page, "/")) {
      await page.waitForURL(/\/(events\/[^/]+\/|setup)/);
      return;
    }
    // The stored session is gone (new database, logged out): sign in again.
    await context.clearCookies();
    await apiLogin(context.request, role);
  }
  throw new Error(`could not open the app as ${role}`);
}

/** A tiny authenticated API client for test setup (not for the flow under test). */
export interface Api {
  get: (url: string) => Promise<any>;
  post: (url: string, data?: unknown) => Promise<any>;
  put: (url: string, data?: unknown) => Promise<any>;
  patch: (url: string, data?: unknown) => Promise<any>;
}

async function apiClient(role: Role): Promise<{ api: Api; dispose: () => Promise<void> }> {
  const key = `${role}-api`;
  const context = await playwrightRequest.newContext({ storageState: { cookies: readCookies(key), origins: [] } });
  let token: string;
  const refreshed = await postWithRateLimit(context, `${API_URL}/auth/refresh`, {});
  if (refreshed.ok()) token = (await refreshed.json()).access_token;
  else token = await apiLogin(context, role);
  writeCookies(key, (await context.storageState()).cookies);

  const call = (method: "get" | "post" | "put" | "patch") => async (url: string, data?: unknown) => {
    const response = await context[method](`${API_URL}${url}`, {
      headers: { Authorization: `Bearer ${token}` },
      ...(data === undefined ? {} : { data }),
    });
    if (!response.ok()) throw new Error(`${method.toUpperCase()} ${url} → ${response.status()} ${await response.text()}`);
    return response.status() === 204 ? null : response.json();
  };
  return {
    api: { get: call("get"), post: call("post"), put: call("put"), patch: call("patch") },
    dispose: () => context.dispose(),
  };
}

interface Sessions {
  /** Open the app as `role` in the test's own page (or `target`). */
  signIn: (role: Role, target?: Page) => Promise<Page>;
  /** A second browser (own cookies and storage) signed in as `role`. */
  open: (role: Role) => Promise<Page>;
  /** An API client signed in as `role`, for arranging test data. */
  api: (role: Role) => Promise<Api>;
  /** Do not hand this page's session on (e.g. after logging out). */
  discard: (page: Page) => void;
}

export const test = base.extend<{ sessions: Sessions }>({
  sessions: async ({ page, browser }, use, testInfo) => {
    const opened = new Map<BrowserContext, { role: Role; keep: boolean; own: boolean }>();
    const clients: Array<() => Promise<void>> = [];
    const sessions: Sessions = {
      async signIn(role, target = page) {
        const own = opened.get(target.context())?.own ?? false;
        opened.set(target.context(), { role, keep: true, own });
        await openApp(target, role);
        return target;
      },
      async open(role) {
        const context = await (browser as Browser).newContext(projectContextOptions(testInfo));
        const newPage = await context.newPage();
        opened.set(context, { role, keep: true, own: true });
        await openApp(newPage, role);
        return newPage;
      },
      async api(role) {
        const client = await apiClient(role);
        clients.push(client.dispose);
        return client.api;
      },
      discard(target) {
        const entry = opened.get(target.context());
        if (entry) entry.keep = false;
      },
    };
    await use(sessions);
    for (const [context, { role, keep, own }] of opened) {
      if (keep) {
        const cookies = await context.cookies().catch(() => [] as Cookies);
        if (cookies.length) writeCookies(role, cookies);
        else forgetCookies(role);
      } else {
        forgetCookies(role);
      }
      if (own) await context.close();
    }
    for (const dispose of clients) await dispose();
  },
});

export { expect };

/** The sidebar navigation (on phones behind the menu button). */
export function mainNav(page: Page) {
  return page.getByRole("navigation", { name: /hauptnavigation|main navigation/i });
}

/** Follow a sidebar link; on narrow screens the menu is opened first. */
export async function openNav(page: Page, name: RegExp) {
  const menu = page.getByRole("button", { name: /menü öffnen|open menu/i });
  const nav = mainNav(page).filter({ visible: true });
  await expect(menu.or(nav).first()).toBeVisible();
  if (await menu.isVisible()) await menu.click();
  await nav.getByRole("link", { name }).click();
}

/** Id of the event the page currently shows. */
export function currentEventId(page: Page): string {
  const match = new URL(page.url()).pathname.match(/^\/events\/([^/]+)/);
  if (!match) throw new Error(`not on an event page: ${page.url()}`);
  return match[1];
}

/**
 * Navigate to `path` inside the current event without reloading: a reload
 * would restore the session again, and /auth/refresh is rate limited too.
 */
export async function gotoInEvent(page: Page, path: string) {
  const target = `/events/${currentEventId(page)}${path}`;
  await page.evaluate((url) => {
    window.history.pushState({}, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, target);
  await page.waitForURL((url) => url.pathname === target.split("?")[0]);
}

/** A minimal but valid PDF (the backend checks the %PDF- signature). */
export function pdfFile(name = "paper.pdf") {
  const body = [
    "%PDF-1.4",
    "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
    "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
    "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj",
    "trailer << /Root 1 0 R >>",
    "%%EOF",
  ].join("\n");
  return { name, mimeType: "application/pdf", buffer: Buffer.from(body) };
}

/** A tiny ASCII STL for print jobs. */
export function stlFile(name: string) {
  const body = [
    "solid e2e",
    "facet normal 0 0 1",
    "outer loop",
    "vertex 0 0 0",
    "vertex 1 0 0",
    "vertex 0 1 0",
    "endloop",
    "endfacet",
    "endsolid e2e",
  ].join("\n");
  return { name, mimeType: "model/stl", buffer: Buffer.from(body) };
}

/** Unique suffix so reruns and retries never collide with earlier data. */
export function uniqueSuffix() {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
}
