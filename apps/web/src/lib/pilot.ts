/**
 * Navigation outside the object screen. The object screen does not read this flag:
 * its pilot layout stays on, and enabled features only add more-menu tabs. Demo mode uses the full screen.
 */
export const PILOT_MODE = process.env.NEXT_PUBLIC_PILOT_MODE === "1";

export function canEditProject(
  user: { id: string; role: string } | null | undefined,
  project: { owner_id?: string | null; contractor_id?: string | null },
  directory: { user_id?: string }[],
) {
  if (!user) return false;
  if (user.role === "admin") return true;
  if (project.owner_id && project.owner_id === user.id) return true;
  if (project.contractor_id && project.contractor_id === user.id) return true;
  return directory.some((row) => row.user_id && row.user_id === user.id);
}
