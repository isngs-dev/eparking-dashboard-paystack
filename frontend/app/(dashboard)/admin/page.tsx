import { redirect } from "next/navigation";
import { backendFetch } from "@/lib/api/backendFetch";
import { getCurrentUser } from "@/lib/auth/session";
import { PageHeader } from "@/components/shell/PageHeader";
import { CreateUserForm, EditPasswordForm } from "./AdminForms";
import { updateUserAction } from "./actions";
import styles from "./admin.module.css";

interface AdminUser {
  id: number;
  email: string;
  role: "ADMIN" | "VIEWER";
  display_name: string;
  organization: "AICL" | "GSDS" | null;
  is_active: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

interface UserListResponse {
  items: AdminUser[];
}

function formatDate(value?: string | null): string {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

export default async function AdminPage() {
  const currentUser = await getCurrentUser();

  if (!currentUser) {
    redirect("/login?next=/admin");
  }

  if (currentUser.role !== "ADMIN") {
    redirect("/");
  }

  const users = await backendFetch<UserListResponse>("/admin/users", {
    revalidate: false,
  });

  return (
    <main>
      <PageHeader title="Admin" tag="Users" />
      <div className={styles.stage}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Create User</h2>
          </div>
          <CreateUserForm />
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Users</h2>
            <span>{users.items.length} total</span>
          </div>

          <div className={styles.table}>
            <div className={styles.headerRow}>
              <span>User</span>
              <span>Role</span>
              <span>Organization</span>
              <span>Status</span>
              <span>Last Login</span>
              <span>Actions</span>
            </div>
            {users.items.map((user) => {
              const updateFormId = `update-user-${user.id}`;
              return (
                <div key={user.id} className={styles.userRow}>
                  <form id={updateFormId} action={updateUserAction} className={styles.rowEdit}>
                    <input type="hidden" name="user_id" value={user.id} />
                    <div className={styles.identityCell}>
                      <input
                        name="display_name"
                        defaultValue={user.display_name}
                        aria-label={`${user.email} display name`}
                      />
                      <span>{user.email}</span>
                    </div>
                    <select name="role" defaultValue={user.role} aria-label={`${user.email} role`}>
                      <option value="VIEWER">VIEWER</option>
                      <option value="ADMIN">ADMIN</option>
                    </select>
                    <select
                      name="organization"
                      defaultValue={user.organization ?? ""}
                      aria-label={`${user.email} organization`}
                    >
                      <option value="">None</option>
                      <option value="AICL">AICL</option>
                      <option value="GSDS">GSDS</option>
                    </select>
                    <select
                      name="is_active"
                      defaultValue={String(user.is_active)}
                      aria-label={`${user.email} status`}
                    >
                      <option value="true">Active</option>
                      <option value="false">Inactive</option>
                    </select>
                    <div className={styles.dateCell}>
                      <span>{formatDate(user.last_login_at)}</span>
                    </div>
                  </form>
                  <div className={styles.actionCell}>
                    <button type="submit" form={updateFormId} className={styles.secondaryButton}>
                      Save
                    </button>
                    <EditPasswordForm userId={user.id} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
