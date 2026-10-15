"use client";

import { useLocale } from "./locale-context";
import Segmented from "./ui/segmented";

export default function LocaleSwitcher() {
  const { locale, setLocale } = useLocale();
  return (
    <Segmented
      size="sm"
      options={[
        { value: "en", label: "EN" },
        { value: "zh", label: "中文" },
      ]}
      value={locale}
      onChange={setLocale}
    />
  );
}
