"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { loginRequest, parseSetCookie } from "@/lib/auth/login";
import type { LoginFormState } from "./types";

/**
 * Server action backing the login form. Runs entirely server-side -- the
 * password is submitted via a native form POST into this action, never via
 * a client-side `fetch` (per sprint §10). Do not add any console.log of
 * `password` or the raw form data here or in `lib/auth/login.ts`.
 */
export async function loginAction(_prevState: LoginFormState, formData: FormData): Promise<LoginFormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const nextPath = sanitizeNextPath(String(formData.get("next") ?? "/"));

  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  const result = await loginRequest(email, password);

  if (!result.ok) {
    return { error: result.detail || "Invalid email or password." };
  }

  if (result.setCookie) {
    const parsed = parseSetCookie(result.setCookie);
    if (parsed) {
      cookies().set({
        name: parsed.name,
        value: parsed.value,
        httpOnly: parsed.httpOnly,
        secure: parsed.secure,
        sameSite: parsed.sameSite,
        path: parsed.path ?? "/",
        // No maxAge relayed on purpose: the backend issues a session cookie
        // (no Max-Age/Expires), matching the sprint's "session cookie, no
        // Max-Age" decision (§4). If the backend ever adds one, `parsed.maxAge`
        // is already threaded through here.
        ...(parsed.maxAge !== undefined ? { maxAge: parsed.maxAge } : {}),
      });
    }
  }

  redirect(nextPath);
}

function sanitizeNextPath(path: string): string {
  if (!path || !path.startsWith("/") || path.startsWith("//")) {
    return "/";
  }
  if (path === "/login" || path.startsWith("/login?")) {
    return "/";
  }
  return path;
}
