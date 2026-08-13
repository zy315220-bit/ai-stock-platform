import type { MetadataRoute } from "next";

import { getSiteUrl } from "@/lib/site";


export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = getSiteUrl();

  return [
    {
      url: siteUrl.toString(),
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 1,
    },
  ];
}
