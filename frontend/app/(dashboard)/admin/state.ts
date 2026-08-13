export interface AdminActionState {
  ok: boolean;
  message: string | null;
}

export const initialAdminActionState: AdminActionState = {
  ok: false,
  message: null,
};
