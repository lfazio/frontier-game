// The token lives in sessionStorage: a tab, not a machine. Nothing else about the player is
// cached — the server owns every number the client shows (UX §1.1).
const KEY = "frontier.token";

export const session = {
  token: (): string | null => sessionStorage.getItem(KEY),
  begin: (token: string): void => sessionStorage.setItem(KEY, token),
  end: (): void => sessionStorage.removeItem(KEY),
};
