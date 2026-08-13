"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { apiBaseUrl, originHeader } from "@/lib/api/backendConfig";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import { getCurrentUser } from "@/lib/auth/session";
import type { AdminActionState } from "./state";

async function adminRequest<T>(
  path: string,
  init: {
    method: "POST" | "PATCH";
    body?: Record<string, unknown>;
  }
): Promise<{ ok: true; body: T } | { ok: false; message: string }> {
  const user = await getCurrentUser();
  if (!user || user.role !== "ADMIN") {
    return { ok: false, message: "Only ADMIN users can manage accounts." };
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Origin: originHeader(),
  };

  const sessionCookie = cookies().get(SESSION_COOKIE_NAME);
  if (sessionCookie) {
    headers.Cookie = `${SESSION_COOKIE_NAME}=${sessionCookie.value}`;
  }

  if (process.env.ADMIN_API_KEY) {
    headers["X-API-Key"] = process.env.ADMIN_API_KEY;
  }

  let res: Response;
  try {
    res = await fetch(new URL(path, apiBaseUrl()), {
      method: init.method,
      headers,
      body: init.body ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
    });
  } catch (err) {
    return {
      ok: false,
      message: `Could not reach the API: ${(err as Error).message}`,
    };
  }

  let body: Record<string, unknown> = {};
  try {
    body = await res.json();
  } catch {
    // Keep generic fallback below.
  }

  if (!res.ok) {
    const detail = body.detail;
    return {
      ok: false,
      message:
        typeof detail === "string"
          ? detail
          : detail
            ? JSON.stringify(detail)
            : `Request failed with status ${res.status}.`,
    };
  }

  return { ok: true, body: body as T };
}

export async function createUserAction(
  _prevState: AdminActionState,
  formData: FormData
): Promise<AdminActionState> {
  const email = String(formData.get("email") ?? "").trim();
  const displayName = String(formData.get("display_name") ?? "").trim();
  const role = String(formData.get("role") ?? "");
  const organizationValue = String(formData.get("organization") ?? "");
  const organization = organizationValue === "" ? null : organizationValue;
  const password = String(formData.get("password") ?? "");
  const confirmPassword = String(formData.get("confirm_password") ?? "");

  if (!email || !displayName) {
    return { ok: false, message: "Email and display name are required." };
  }
  if (!password) {
    return { ok: false, message: "Password is required." };
  }
  if (password !== confirmPassword) {
    return { ok: false, message: "Passwords do not match." };
  }

  const result = await adminRequest<{ user: { id: number } }>("/admin/users", {
    method: "POST",
    body: {
      email,
      display_name: displayName,
      role,
      organization,
      password,
    },
  });

  if (!result.ok) {
    return { ok: false, message: result.message };
  }

  revalidatePath("/admin");
  return {
    ok: true,
    message: "User created successfully.",
  };
}

export async function updateUserAction(formData: FormData): Promise<void> {
  const userId = Number(formData.get("user_id"));
  const organizationValue = String(formData.get("organization") ?? "");

  if (!Number.isInteger(userId)) {
    return;
  }

  await adminRequest(`/admin/users/${userId}`, {
    method: "PATCH",
    body: {
      role: String(formData.get("role") ?? ""),
      display_name: String(formData.get("display_name") ?? "").trim(),
      organization: organizationValue === "" ? null : organizationValue,
      is_active: formData.get("is_active") === "true",
    },
  });

  revalidatePath("/admin");
}

export async function updatePasswordAction(
  _prevState: AdminActionState,
  formData: FormData
): Promise<AdminActionState> {
  const userId = Number(formData.get("user_id"));
  if (!Number.isInteger(userId)) {
    return { ok: false, message: "Invalid user id." };
  }
  const newPassword = String(formData.get("new_password") ?? "");
  const confirmPassword = String(formData.get("confirm_password") ?? "");

  if (!newPassword) {
    return { ok: false, message: "New password is required." };
  }
  if (newPassword !== confirmPassword) {
    return { ok: false, message: "Passwords do not match." };
  }

  const result = await adminRequest<{ user: { id: number } }>(
    `/admin/users/${userId}/password`,
    { method: "PATCH", body: { new_password: newPassword } }
  );

  if (!result.ok) {
    return { ok: false, message: result.message };
  }

  revalidatePath("/admin");
  return {
    ok: true,
    message: "Password updated. The user has been signed out of existing sessions.",
  };
}
