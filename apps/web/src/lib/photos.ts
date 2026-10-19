export const PHOTO_MAX_EDGE = 1600;
export const PHOTO_JPEG_QUALITY = 0.8;

function preparedName(name: string) {
  const base = name.replace(/\.[^.]+$/, "") || "photo";
  return `${base}.anyq.jpg`;
}

export function isPreparedPhoto(file: File) {
  return file.type === "image/jpeg" && file.name.endsWith(".anyq.jpg");
}

/** Resize a photo to a JPEG before upload. Non-images and failures pass through. */
export async function preparePhoto(file: File): Promise<File> {
  if (typeof document === "undefined" || typeof createImageBitmap !== "function") return file;
  if (!file.type.startsWith("image/") || file.type === "image/gif" || file.type === "image/svg+xml") return file;
  if (isPreparedPhoto(file)) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const longest = Math.max(bitmap.width, bitmap.height) || 1;
    const scale = longest > PHOTO_MAX_EDGE ? PHOTO_MAX_EDGE / longest : 1;
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bitmap.close?.();
      return file;
    }
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", PHOTO_JPEG_QUALITY);
    });
    if (!blob) return file;
    return new File([blob], preparedName(file.name), { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return file;
  }
}

export async function preparePhotos(files: File[]) {
  const prepared: File[] = [];
  for (const file of files) prepared.push(await preparePhoto(file));
  return prepared;
}
