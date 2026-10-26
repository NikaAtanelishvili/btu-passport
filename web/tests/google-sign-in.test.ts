// FE-05: the Google button and the callback errors on /login.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GoogleSignIn } from "@/components/google-sign-in";
import { GOOGLE_ERRORS, googleErrorMessage, googleStartUrl } from "@/lib/google-sign-in";

const render = (props: Parameters<typeof GoogleSignIn>[0]) =>
  renderToStaticMarkup(createElement(GoogleSignIn, props));

describe("GoogleSignIn", () => {
  it("shows the branded button and the divider when Google is configured", () => {
    const html = render({ enabled: true, next: "/checkin/abc" });
    expect(html).toContain("Sign in with Google");
    expect(html).toContain('href="/auth/google/start?next=%2Fcheckin%2Fabc"');
    expect(html).toContain("#4285F4"); // the official multicolour G
    expect(html).toMatch(/>or</);
  });

  it("hides the button without a client ID", () => {
    const html = render({ enabled: false });
    expect(html).not.toContain("Sign in with Google");
    expect(html).not.toContain("/auth/google/start");
  });

  it.each(Object.keys(GOOGLE_ERRORS))("shows the message for %s", (code) => {
    expect(render({ enabled: true, error: code })).toContain(
      GOOGLE_ERRORS[code].replaceAll("'", "&#x27;"),
    );
  });

  it("ignores unknown error codes", () => {
    expect(googleErrorMessage("<script>")).toBeNull();
    expect(render({ enabled: true, error: "<script>" })).not.toContain("Not signed in");
  });
});

describe("googleStartUrl", () => {
  it("passes next on, encoded", () => {
    expect(googleStartUrl()).toBe("/auth/google/start");
    expect(googleStartUrl("/me?x=1&y=2")).toBe("/auth/google/start?next=%2Fme%3Fx%3D1%26y%3D2");
  });
});
