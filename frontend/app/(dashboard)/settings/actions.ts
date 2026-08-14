"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { apiBaseUrl, originHeader } from "@/lib/api/backendConfig";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import { changePasswordRequest, parseSetCookie } from "@/lib/auth/login";
import type { SettingsActionState } from "./state";

function sessionCookieHeader(): string | null {
  const sessionCookie = cookies().get(SESSION_COOKIE_NAME);
  return sessionCookie
    ? `${SESSION_COOKIE_NAME}=${sessionCookie.value}`
    : null;
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export async function updateProfileAction(
  _previous: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const displayName = String(formData.get("display_name") ?? "").trim();
  if (!displayName) {
    return { ok: false, message: "Display name is required." };
  }
  if (displayName.length > 120) {
    return { ok: false, message: "Display name must be 120 characters or fewer." };
  }

  const cookieHeader = sessionCookieHeader();
  if (!cookieHeader) {
    return { ok: false, message: "Your session has expired. Please sign in again." };
  }

  let res: Response;
  try {
    res = await fetch(new URL("/auth/me", apiBaseUrl()), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Origin: originHeader(),
        Cookie: cookieHeader,
      },
      body: JSON.stringify({ display_name: displayName }),
      cache: "no-store",
    });
  } catch (error) {
    return {
      ok: false,
      message: `Could not reach the API: ${(error as Error).message}`,
    };
  }

  if (!res.ok) {
    return {
      ok: false,
      message: await errorDetail(res, "Unable to update your profile."),
    };
  }

  revalidatePath("/", "layout");
  return { ok: true, message: "Name updated successfully." };
}

export async function updateOwnPasswordAction(
  _previous: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const currentPassword = String(formData.get("current_password") ?? "");
  const newPassword = String(formData.get("new_password") ?? "");
  const confirmPassword = String(formData.get("confirm_password") ?? "");

  if (!currentPassword || !newPassword || !confirmPassword) {
    return { ok: false, message: "All password fields are required." };
  }
  if (newPassword !== confirmPassword) {
    return { ok: false, message: "New password and confirmation do not match." };
  }

  const cookieHeader = sessionCookieHeader();
  if (!cookieHeader) {
    return { ok: false, message: "Your session has expired. Please sign in again." };
  }

  const result = await changePasswordRequest(
    cookieHeader,
    currentPassword,
    newPassword,
  );
  if (!result.ok) {
    return { ok: false, message: result.detail || "Unable to change password." };
  }

  if (!result.setCookie) {
    return {
      ok: false,
      message: "Password changed, but the replacement session was not returned. Please sign in again.",
    };
  }

  const replacement = parseSetCookie(result.setCookie);
  if (!replacement) {
    return {
      ok: false,
      message: "Password changed, but the replacement session was invalid. Please sign in again.",
    };
  }

  cookies().set({
    name: replacement.name,
    value: replacement.value,
    httpOnly: replacement.httpOnly,
    secure: replacement.secure,
    sameSite: replacement.sameSite,
    path: replacement.path ?? "/",
    ...(replacement.maxAge !== undefined
      ? { maxAge: replacement.maxAge }
      : {}),
  });

  return {
    ok: true,
    message: "Password updated. Other signed-in sessions have been logged out.",
  };
}
