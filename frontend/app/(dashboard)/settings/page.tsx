import { redirect } from "next/navigation";
import { PageHeader } from "@/components/shell/PageHeader";
import { getCurrentUser } from "@/lib/auth/session";
import { PasswordForm, ProfileForm } from "./SettingsForms";
import styles from "./settings.module.css";

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login?next=/settings");

  return (
    <main>
      <PageHeader title="Settings" tag="Account" />
      <div className={styles.stage}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2>Profile</h2>
              <p>Update the name shown throughout the dashboard.</p>
            </div>
          </div>
          <ProfileForm user={user} />
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2>Password</h2>
              <p>Change your password securely using your current password.</p>
            </div>
          </div>
          <PasswordForm />
        </section>
      </div>
    </main>
  );
}
