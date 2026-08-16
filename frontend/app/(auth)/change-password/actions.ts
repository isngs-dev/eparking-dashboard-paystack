"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { changePasswordRequest, parseSetCookie } from "@/lib/auth/login";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import type { ChangePasswordFormState } from "./types";

/**
 * Server action backing the mandatory first-login password change. Requires an
 * existing session cookie (forwarded explicitly -- server actions don't run
 * in the browser's fetch context, so cookies must be read via `cookies()`
 * and attached manually). Never logs password fields.
 */
export async function changePasswordAction(
  _prevState: ChangePasswordFormState,
  formData: FormData
): Promise<ChangePasswordFormState> {
  const currentPassword = String(formData.get("current_password") ?? "");
  const newPassword = String(formData.get("new_password") ?? "");
  const confirmPassword = String(formData.get("confirm_password") ?? "");

  if (!currentPassword || !newPassword || !confirmPassword) {
    return { error: "All fields are required." };
  }

  if (newPassword !== confirmPassword) {
    return { error: "New password and confirmation do not match." };
  }

  const sessionCookie = cookies().get(SESSION_COOKIE_NAME);
  if (!sessionCookie) {
    return { error: "Your session has expired. Please sign in again." };
  }

  const cookieHeader = `${SESSION_COOKIE_NAME}=${sessionCookie.value}`;
  const result = await changePasswordRequest(cookieHeader, currentPassword, newPassword);

  if (!result.ok) {
    return { error: result.detail || "Unable to change password." };
  }

  if (!result.setCookie) {
    return {
      error: "Password changed, but your replacement session was not returned. Please sign in again.",
    };
  }

  const replacement = parseSetCookie(result.setCookie);
  if (!replacement) {
    return {
      error: "Password changed, but your replacement session was invalid. Please sign in again.",
    };
  }

  cookies().set({
    name: replacement.name,
    value: replacement.value,
    httpOnly: replacement.httpOnly,
    secure: replacement.secure,
    sameSite: replacement.sameSite,
    path: replacement.path ?? "/",
    ...(replacement.maxAge !== undefined ? { maxAge: replacement.maxAge } : {}),
  });

  redirect("/");
}
