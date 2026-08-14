export interface SettingsActionState {
  ok: boolean;
  message: string | null;
}

export const initialSettingsActionState: SettingsActionState = {
  ok: false,
  message: null,
};
