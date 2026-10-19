import Image from "next/image";

function localPhoto(src: string) {
  return src.startsWith("/") && !src.startsWith("/v1/") && !src.startsWith("/uploads/") && !src.startsWith("/blob");
}

export function PhotoView({
  src,
  alt = "",
  className,
  sizes = "(max-width: 640px) 100vw, 640px",
}: {
  src: string;
  alt?: string;
  className?: string;
  sizes?: string;
}) {
  if (localPhoto(src)) {
    return <Image src={src} alt={alt} width={960} height={640} sizes={sizes} className={className} />;
  }
  return (
    // Authenticated, blob, and remote URLs stay on a plain image so the request can carry a session.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} width={960} height={640} decoding="async" loading="lazy" className={className} />
  );
}
