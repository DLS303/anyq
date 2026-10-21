import Link from "next/link";
import { preload } from "react-dom";
import type { Locale } from "@/lib/types";
import styles from "./HomeStage.module.css";

const SIZES = "100vw";

const mobileAvif =
  "/hero/mobile-390.avif 390w, /hero/mobile-640.avif 640w, /hero/mobile-828.avif 828w, /hero/mobile-1080.avif 1080w";
const mobileWebp =
  "/hero/mobile-390.webp 390w, /hero/mobile-640.webp 640w, /hero/mobile-828.webp 828w, /hero/mobile-1080.webp 1080w";
const mobileJpg =
  "/hero/mobile-390.jpg 390w, /hero/mobile-640.jpg 640w, /hero/mobile-828.jpg 828w, /hero/mobile-1080.jpg 1080w";
const desktopAvif = "/hero/desktop-768.avif 768w, /hero/desktop-1280.avif 1280w, /hero/desktop-1920.avif 1920w";
const desktopWebp = "/hero/desktop-768.webp 768w, /hero/desktop-1280.webp 1280w, /hero/desktop-1920.webp 1920w";
const desktopJpg = "/hero/desktop-768.jpg 768w, /hero/desktop-1280.jpg 1280w, /hero/desktop-1920.jpg 1920w";

const blur = {
  mobile:
    "data:image/jpeg;base64,/9j/2wBDABQUFBQVFBcZGRcfIh4iHy4rJycrLkYyNjI2MkZqQk5CQk5Cal5yXVZdcl6phXZ2hanDpJukw+zT0+z/////////2wBDARQUFBQVFBcZGRcfIh4iHy4rJycrLkYyNjI2MkZqQk5CQk5Cal5yXVZdcl6phXZ2hanDpJukw+zT0+z/////////wgARCAAkABQDASIAAhEBAxEB/8QAGgABAAIDAQAAAAAAAAAAAAAAAAIEAQMGBf/EABcBAQEBAQAAAAAAAAAAAAAAAAMBAAL/2gAMAwEAAhADEAAAAOXxYgnFdNt0dbxog19QKeuJKFn/xAAeEAADAAEEAwAAAAAAAAAAAAAAAQIDBBESMRATIv/aAAgBAQABPwDgOBo9dyOaY4ZqMukiuLRT0dL5Y1g37Ly1fYqa6Zzofjc//8QAGhEAAQUBAAAAAAAAAAAAAAAAAgEQESAhQf/aAAgBAgEBPwDGAI6tP//EABkRAAEFAAAAAAAAAAAAAAAAAAIQESAhQf/aAAgBAwEBPwC0I3yH/9k=",
  desktop:
    "data:image/jpeg;base64,/9j/2wBDABQUFBQVFBcZGRcfIh4iHy4rJycrLkYyNjI2MkZqQk5CQk5Cal5yXVZdcl6phXZ2hanDpJukw+zT0+z/////////2wBDARQUFBQVFBcZGRcfIh4iHy4rJycrLkYyNjI2MkZqQk5CQk5Cal5yXVZdcl6phXZ2hanDpJukw+zT0+z/////////wgARCAASACADASIAAhEBAxEB/8QAGQAAAgMBAAAAAAAAAAAAAAAAAAMCBQYE/8QAFwEBAQEBAAAAAAAAAAAAAAAAAwABAv/aAAwDAQACEAMQAAAAzFlTu6zSdeUYS17QUpRCv//EAB4QAAICAgIDAAAAAAAAAAAAAAECAAMEEiIyEBNB/9oACAEBAAE/AK9fsp9URsVRyMpXHtPFhAYrkTfbsYlzp0eCDz//xAAYEQEAAwEAAAAAAAAAAAAAAAACAAEQMf/aAAgBAgEBPwCIq+Lf/8QAGBEAAgMAAAAAAAAAAAAAAAAAAQIAEEH/2gAIAQMBAT8AisBl/wD/2Q==",
};

const copy = {
  ru: {
    title: "Закупки для стройки — быстрее и дешевле",
    lead: "Сравнивайте цены поставщиков, оставляйте заявку в 3 нажатия и смотрите бюджет: план и факт.",
    register: "Зарегистрироваться",
    login: "Войти",
    alt: "Строительная площадка на закате: каркас здания, башенный кран и поставка материалов",
  },
  kk: {
    title: "Құрылыс сатып алулары — тезірек және арзанырақ",
    lead: "Жеткізуші бағасын салыстырыңыз, өтінімді 3 рет басып жіберіңіз, бюджетті жоспар мен факт бойынша қараңыз.",
    register: "Тіркелу",
    login: "Кіру",
    alt: "Ымырттағы құрылыс алаңы: ғимарат қаңқасы, мұнаралы кран және материал жеткізу",
  },
} as const;

export function HomeStage({ locale }: { locale: Locale }) {
  const text = copy[locale];

  preload("/hero/mobile-828.avif", {
    as: "image",
    fetchPriority: "high",
    type: "image/avif",
    media: "(max-width: 767px)",
    imageSrcSet: mobileAvif,
    imageSizes: SIZES,
  });
  preload("/hero/desktop-1280.avif", {
    as: "image",
    fetchPriority: "high",
    type: "image/avif",
    media: "(min-width: 768px)",
    imageSrcSet: desktopAvif,
    imageSizes: SIZES,
  });

  return (
    <section className={styles.hero} aria-labelledby="landing-hero-title">
      <div
        className={styles.media}
        style={{
          ["--hero-blur-mobile" as string]: `url("${blur.mobile}")`,
          ["--hero-blur-desktop" as string]: `url("${blur.desktop}")`,
        }}
      >
        <picture>
          <source media="(max-width: 767px)" type="image/avif" srcSet={mobileAvif} sizes={SIZES} />
          <source media="(max-width: 767px)" type="image/webp" srcSet={mobileWebp} sizes={SIZES} />
          <source media="(min-width: 768px)" type="image/avif" srcSet={desktopAvif} sizes={SIZES} />
          <source media="(min-width: 768px)" type="image/webp" srcSet={desktopWebp} sizes={SIZES} />
          <source media="(max-width: 767px)" type="image/jpeg" srcSet={mobileJpg} sizes={SIZES} />
          <source media="(min-width: 768px)" type="image/jpeg" srcSet={desktopJpg} sizes={SIZES} />
          <img
            src="/hero/mobile-828.jpg"
            alt={text.alt}
            width={828}
            height={1472}
            fetchPriority="high"
            decoding="async"
          />
        </picture>
      </div>
      <div className={styles.scrim} aria-hidden="true" />
      <div className={styles.copy}>
        <h1 id="landing-hero-title" className={styles.title}>
          {text.title}
        </h1>
        <p className={styles.lead}>{text.lead}</p>
        <div className={styles.actions}>
          <Link href={`/${locale}/login?mode=register`} className={styles.primary}>
            {text.register}
          </Link>
          <Link href={`/${locale}/login?mode=login`} className={styles.secondary}>
            {text.login}
          </Link>
        </div>
      </div>
    </section>
  );
}
