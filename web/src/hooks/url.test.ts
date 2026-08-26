import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_URL_STATE,
  decodeUrl,
  encodeUrl,
  saveUrl,
  watchUrl,
  type AtlasUrlState,
} from "./url";
import type { CameraView } from "../lib/camera";

type TestHost = Parameters<typeof saveUrl>[2] & EventTarget;

function makeHost(href = "https://example.com/atlas/"): TestHost {
  const target = new EventTarget() as TestHost;
  target.location = { href };
  target.history = {
    replaceState: vi.fn((_data, _unused, next) => {
      target.location.href = new URL(String(next), target.location.href).toString();
    }),
    pushState: vi.fn((_data, _unused, next) => {
      target.location.href = new URL(String(next), target.location.href).toString();
    }),
  };
  return target;
}

function fullState(): AtlasUrlState {
  return {
    view: "library",
    query: "world models",
    selected: "paper:2401.01234",
    kinds: ["topic", "paper", "idea"],
    minFeasibility: 6.5,
    focus: "topic:world-models",
    layout: "connections",
    camera: null,
  };
}

describe("atlas URLs", () => {
  it("enables papers by default and preserves an explicit papers-off lens", () => {
    expect(DEFAULT_URL_STATE.kinds).toEqual(["topic", "trick", "paper", "idea"]);
    expect(decodeUrl("https://example.com/atlas/").kinds).toEqual(
      DEFAULT_URL_STATE.kinds,
    );
    expect(decodeUrl("https://example.com/atlas/#?k=tri").kinds).toEqual([
      "topic",
      "trick",
      "idea",
    ]);
  });

  it("round trips every shareable state field with compact parameters", () => {
    const url = encodeUrl(fullState(), "https://example.com/atlas/?old=value#map");
    expect(url.search).toBe("");
    expect(url.hash).toBe(
      "#?v=l&q=world+models&s=paper%3A2401.01234&k=tpi&f=6.5&x=topic%3Aworld-models&l=c",
    );
    expect(decodeUrl(url)).toEqual(fullState());
  });

  it("omits defaults and can encode an empty lens set", () => {
    expect(
      encodeUrl(DEFAULT_URL_STATE, "https://example.com/atlas/?q=private#section").href,
    ).toBe("https://example.com/atlas/#section");
    const url = encodeUrl({ ...DEFAULT_URL_STATE, kinds: [] }, "https://example.com/");
    expect(url.hash).toBe("#?k=-");
    expect(decodeUrl(url).kinds).toEqual([]);
  });

  it("round trips a bounded camera snapshot in the fragment", () => {
    const camera: CameraView = {
      target: [12.3, -45.6, 0],
      radius: 90,
      yaw: 35,
      pitch: -20,
    };
    const url = encodeUrl(
      { ...DEFAULT_URL_STATE, camera },
      "https://example.com/atlas/",
    );
    expect(url.hash).toBe("#?c=1_12.3_-45.6_0_90_35_-20");
    expect(decodeUrl(url).camera).toEqual(camera);
  });

  it("ignores malformed camera state without losing valid filters", () => {
    const state = decodeUrl("https://example.com/atlas/#?q=world&c=1_NaN_0_0_1_0_0");
    expect(state.query).toBe("world");
    expect(state.camera).toBeNull();
  });

  it("falls back safely for malformed and out-of-range parameters", () => {
    const state = decodeUrl(
      "https://example.com/atlas/#?v=nope&q=%00bad&s=%3Cscript%3E&k=ttz&f=10.5&x=%2Fbad&l=x",
    );
    expect(state).toEqual(DEFAULT_URL_STATE);
    expect(decodeUrl("http://[")).toEqual(DEFAULT_URL_STATE);
  });

  it("replaces exploration state without adding a history entry", () => {
    const host = makeHost();
    saveUrl(fullState(), "replace", host);
    expect(host.history.replaceState).toHaveBeenCalledOnce();
    expect(host.history.pushState).not.toHaveBeenCalled();
    expect(host.location.href).toContain("/atlas/#?v=l&q=world+models");
  });

  it("never reads or emits Atlas state in the request query", () => {
    expect(decodeUrl("https://example.com/atlas/?q=private&f=9")).toEqual(
      DEFAULT_URL_STATE,
    );
    const url = encodeUrl(
      fullState(),
      "https://example.com/atlas/?q=private#unsafe/hash",
    );
    expect(url.search).toBe("");
    expect(url.hash).toContain("#?v=l&q=world+models");
    expect(url.href).not.toContain("private");
  });

  it("restores state on back and forward navigation and removes its listener", () => {
    const host = makeHost("https://example.com/atlas/#?q=first");
    const restore = vi.fn();
    const stop = watchUrl(restore, host);

    host.location.href = "https://example.com/atlas/#?q=back&f=4.5";
    host.dispatchEvent(new Event("popstate"));
    host.location.href = "https://example.com/atlas/#?q=forward&l=c";
    host.dispatchEvent(new Event("popstate"));

    expect(restore).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ query: "back", minFeasibility: 4.5 }),
    );
    expect(restore).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ query: "forward", layout: "connections" }),
    );

    stop();
    host.dispatchEvent(new Event("popstate"));
    expect(restore).toHaveBeenCalledTimes(2);
  });
});
