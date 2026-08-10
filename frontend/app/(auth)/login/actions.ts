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

  // must_change_password enforcement (forcing the redirect target, blocking
  // dashboard access until changed) is Phase 4 scope per the sprint's
  // layout-level check. For Phase 3 we still route the user to the right
  // place immediately after login so the loop is complete end-to-end.
  if (result.mustChangePassword) {
    redirect("/change-password");
  }

  redirect("/");
}
